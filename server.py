# server.py
import os
import threading
import time
import uuid
import secrets
import socket
import nacos
import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from random import random
from typing import Optional, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from gemini_webapi import GeminiClient
from gemini_webapi.constants import Model
from pydantic import BaseModel

try:
    import browser_cookie3
except ImportError:
    browser_cookie3 = None

load_dotenv()

# --- 配置 ---
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))

# 目录配置
IMAGES_BASE_DIR = Path(os.getenv("IMAGES_DIR", "stored_images"))
IMAGES_BASE_DIR.mkdir(exist_ok=True)
CONVERSATIONS_DIR = Path("conversations")
CONVERSATIONS_DIR.mkdir(exist_ok=True)
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)
STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)

# [新增] Cookie 缓存文件路径
COOKIE_CACHE_FILE = Path("cookie_cache.json")
DEBUG = os.getenv("DEBUG", "true").lower() == "true"

# --- 全局变量 ---
gemini_client = None
active_chats = {}

# 🔥 熔断机制变量 🔥
auth_failure_count = 0  # 连续认证失败次数
last_auth_failure_time = 0.0  # 上次失败时间戳

NORMAL_COOL_DOWN = 900        # 常规冷却：15分钟 (针对 401/Cookie失效)
CRITICAL_COOL_DOWN = 3600     # 严重冷却：1小时 (针对 429 限流)
JITTER_SECONDS = 300

EXTERNAL_IP = os.getenv("EXTERNAL_IP")
EXTERNAL_PORT = int(os.getenv("EXTERNAL_PORT")) if os.getenv("EXTERNAL_PORT") else None

def get_container_ip():
    """获取容器在 Docker 网络中的真实 IP"""
    try:
        # 这种方式在 Docker 容器内非常有效
        # 它尝试连接外部地址，从而获得自己对外的路由 IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

NACOS_SERVER_ADDR = os.getenv("NACOS_SERVER_ADDR") # 从 compose.yml 读取
SERVICE_NAME = "gemini-service"
NAMESPACE = "public"
GROUP_NAME = "DEFAULT_GROUP"

# 依赖检查
try:
    import multipart
except ImportError:
    print("=" * 60)
    print("❌ 缺少依赖: python-multipart")
    print("📦 请运行: pip install python-multipart")
    print("=" * 60)
    raise


def debug_log(message: str, level: str = "INFO"):
    """统一的 debug 日志输出"""
    if DEBUG:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        emoji_map = {
            "INFO": "ℹ️", "SUCCESS": "✅", "ERROR": "❌",
            "WARNING": "⚠️", "DEBUG": "🔍", "REQUEST": "📝",
            "RESPONSE": "📤", "IMAGE": "🖼️", "FILE": "📎", "CHAT": "💬"
        }
        emoji = emoji_map.get(level, "•")
        print(f"[{timestamp}] {emoji} {message}")


def get_auto_cookies(force_refresh: bool = False):
    """
    获取 Cookie (支持文件缓存)

    :param force_refresh:
        False (默认) -> 优先读取本地 cookie_cache.json 文件
        True -> 强制从浏览器抓取，并更新到文件
    """
    # 1. [缓存优先] 尝试从本地文件读取
    if not force_refresh and COOKIE_CACHE_FILE.exists():
        try:
            with open(COOKIE_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                psid = data.get("SECURE_1PSID")
                ts = data.get("SECURE_1PSIDTS")

                if psid and ts:
                    debug_log("📂 [缓存命中] 已从 cookie_cache.json 加载 Cookie", "INFO")
                    return psid, ts
        except Exception as e:
            debug_log(f"⚠️ 读取缓存文件失败，将尝试从浏览器获取: {e}", "WARNING")
            # 读取失败不中断，继续往下走去浏览器抓

    # 2. [浏览器抓取]
    if not browser_cookie3:
        debug_log("未安装 browser_cookie3，无法抓取", "WARNING")
        return None, None

    debug_log("🌍 正在从 Kasm Chrome 浏览器抓取最新 Cookie...", "INFO")
    try:
        cj = browser_cookie3.chrome(domain_name='.google.com')
        psid = None
        ts = None

        for cookie in cj:
            if cookie.name == '__Secure-1PSID':
                psid = cookie.value
            if cookie.name == '__Secure-1PSIDTS':
                ts = cookie.value

        if psid and ts:
            debug_log(f"✅ 浏览器抓取成功! TS: {ts[:10]}...", "SUCCESS")

            # 3. [写入缓存] 保存到文件，方便下次使用
            try:
                with open(COOKIE_CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump({
                        "SECURE_1PSID": psid,
                        "SECURE_1PSIDTS": ts,
                        "updated_at": datetime.now().isoformat()
                    }, f, indent=2)
                debug_log("💾 Cookie 已保存到本地缓存文件 (cookie_cache.json)", "SUCCESS")
            except Exception as e:
                debug_log(f"⚠️ 缓存写入失败 (不影响运行): {e}", "WARNING")

            return psid, ts
        else:
            debug_log("❌ 浏览器读取成功但未找到 Gemini Cookie (请确认已登录)", "WARNING")
            return None, None

    except Exception as e:
        debug_log(f"❌ 浏览器抓取失败: {e}", "ERROR")
        return None, None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global gemini_client, auth_failure_count

    # ==========================================
    # 1. 初始化 Gemini 客户端 (Cookie 逻辑) - 保持原样
    # ==========================================
    secure_1psid = os.getenv("SECURE_1PSID")
    secure_1psidts = os.getenv("SECURE_1PSIDTS")

    if not secure_1psid or not secure_1psidts:
        debug_log("尝试加载 Cookie (环境变量 -> 文件缓存 -> 浏览器)...", "INFO")
        auto_psid, auto_ts = get_auto_cookies(force_refresh=False)
        if auto_psid and auto_ts:
            secure_1psid = auto_psid
            secure_1psidts = auto_ts

    try:
        if secure_1psid and secure_1psidts:
            gemini_client = GeminiClient(secure_1psid, secure_1psidts)
            await gemini_client.init(auto_refresh=False)
            debug_log("✅ Gemini 客户端初始化成功", "SUCCESS")
        else:
            debug_log("⚠️ 未获取到 Cookie，将在首次请求时尝试获取", "WARNING")
    except Exception as e:
        debug_log(f"Gemini 初始化失败: {e}", "ERROR")

    # ==========================================
    # 2. Nacos 服务注册逻辑 (包含心跳维持) - [新增修改]
    # ==========================================
    nacos_client = None
    heartbeat_thread = None
    stop_heartbeat = threading.Event()  # 用于优雅停止心跳线程

    # 计算注册 IP (优先使用外部 IP，否则使用容器 IP)
    register_ip = EXTERNAL_IP if EXTERNAL_IP else get_container_ip()
    register_port = EXTERNAL_PORT if EXTERNAL_PORT else PORT

    if NACOS_SERVER_ADDR:
        try:
            debug_log(f"正在向 Nacos ({NACOS_SERVER_ADDR}) 注册服务...", "INFO")
            nacos_client = nacos.NacosClient(NACOS_SERVER_ADDR, namespace=NAMESPACE)

            # --- A. 注册服务 ---
            nacos_client.add_naming_instance(
                SERVICE_NAME,
                register_ip,
                register_port,
                group_name=GROUP_NAME,
                ephemeral=True,  # 临时实例
                metadata={"version": "1.0", "env": "prod", "weight": "1.0"}
            )
            debug_log(f"✅ Nacos 注册成功: {SERVICE_NAME} @ {register_ip}:{register_port}", "SUCCESS")

            # --- B. 定义心跳函数 (运行在后台线程) ---
            def send_heartbeat():
                debug_log("💓 心跳线程已启动", "INFO")
                while not stop_heartbeat.is_set():
                    try:
                        nacos_client.send_heartbeat(
                            SERVICE_NAME,
                            register_ip,
                            register_port,
                            group_name=GROUP_NAME,
                            ephemeral=True
                        )
                        # debug_log("💓 beat...", "DEBUG") # 调试用，太吵可注释
                    except Exception as hb_e:
                        debug_log(f"⚠️ 心跳发送异常: {hb_e}", "WARNING")

                    # Nacos 建议心跳间隔 5 秒
                    # 使用 wait 可以被 stop_event 立即唤醒，比 time.sleep 退出更快
                    stop_heartbeat.wait(5)

            # --- C. 启动心跳线程 ---
            heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)
            heartbeat_thread.start()

        except Exception as e:
            debug_log(f"❌ Nacos 注册或启动心跳失败: {e}", "ERROR")

    # ==========================================
    # 3. 🚀 启动完成，服务开始运行 (Yield)
    # ==========================================
    yield

    # ==========================================
    # 4. 服务关闭时的清理逻辑
    # ==========================================

    # A. 停止心跳线程
    if heartbeat_thread:
        debug_log("正在停止心跳线程...", "INFO")
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=2)

    # B. 从 Nacos 注销
    if nacos_client:
        try:
            debug_log("正在从 Nacos 注销服务...", "INFO")
            nacos_client.remove_naming_instance(
                SERVICE_NAME,
                register_ip,
                register_port,
                group_name=GROUP_NAME
            )
            debug_log("👋 Nacos 注销成功", "SUCCESS")
        except Exception as e:
            debug_log(f"❌ Nacos 注销失败: {e}", "ERROR")


app = FastAPI(lifespan=lifespan, title="Gemini Chat API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: List[Message]
    conversation_id: Optional[str] = None
    files: Optional[List[str]] = None


MODEL_MAP = {
    "gemini-pro": Model.G_2_5_PRO,
    "gemini-2.5-pro": Model.G_2_5_PRO,
    "gemini-2.5-flash": Model.G_2_5_FLASH,
    "gemini-3.0-pro": Model.G_3_0_PRO,
    "default": Model.UNSPECIFIED,
}


def get_today_dir() -> Path:
    now = datetime.now()
    year_month = now.strftime("%Y%m")
    date = now.strftime("%Y%m%d")
    dir_path = IMAGES_BASE_DIR / year_month / date
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def generate_filename() -> str:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_suffix = secrets.token_hex(4)
    return f"{timestamp}_{random_suffix}"


def save_conversation(conversation_id: str, metadata: dict):
    file_path = CONVERSATIONS_DIR / f"{conversation_id}.json"
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    debug_log(f"对话已保存: {conversation_id}", "CHAT")


def load_conversation(conversation_id: str) -> Optional[dict]:
    file_path = CONVERSATIONS_DIR / f"{conversation_id}.json"
    if file_path.exists():
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


@app.get("/", response_class=HTMLResponse)
async def root():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    else:
        return "Frontend not found"


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest, req: Request):
    """
    OpenAI 兼容接口 (支持 Cookie 自动重连 + 429必杀熔断 + 随机抖动 + 文件缓存)
    """
    global gemini_client, auth_failure_count, last_auth_failure_time

    try:
        all_messages = request.messages
        current_msg_content = all_messages[-1].content
        model = MODEL_MAP.get(request.model, Model.UNSPECIFIED)
        conversation_id = request.conversation_id
        files = request.files

        debug_log("=" * 60, "REQUEST")
        debug_log(f"模型: {request.model}", "REQUEST")
        debug_log(f"对话ID: {conversation_id or '新对话'}", "REQUEST")
        debug_log(f"消息: {current_msg_content[:100]}{'...' if len(current_msg_content) > 100 else ''}", "REQUEST")

        # =================================================================
        # --- 0. 客户端检查 (新增 429 熔断与抖动逻辑) ---
        # =================================================================
        # 只有在有失败记录，或者客户端未初始化时才进入检查
        if not gemini_client or auth_failure_count >= 3:

            # 1. 确定冷却策略
            # count >= 100 意味着触发了 429 严重限流，使用长冷却时间
            base_cool_down = CRITICAL_COOL_DOWN if auth_failure_count >= 100 else NORMAL_COOL_DOWN

            # 2. 计算实际冷却时间 (带随机抖动)
            # 实际冷却 = 基础时间 + 随机(0 ~ 300秒)
            actual_cool_down = base_cool_down + random.randint(0, JITTER_SECONDS)

            time_passed = time.time() - last_auth_failure_time

            # 3. 检查是否处于冷却期
            if time_passed < actual_cool_down:
                remaining = int(actual_cool_down - time_passed)
                reason = "Google 严重流控 (429)" if auth_failure_count >= 100 else "认证失效保护"

                error_detail = (
                    f"🔥 {reason} 生效中。系统已强制休眠。"
                    f"请等待约 {remaining} 秒 ({remaining // 60}分钟) 后重试。"
                )
                debug_log(error_detail, "WARNING")
                # 直接拒绝，保护账号
                raise HTTPException(status_code=503, detail=error_detail)

            # 4. 如果冷却时间已过，尝试初始化 (如果 client 是 None)
            if not gemini_client:
                debug_log("客户端未初始化，尝试首次初始化...", "WARNING")
                try:
                    # 首次/冷却后尝试: 优先读缓存 (force_refresh=False)
                    new_psid, new_ts = get_auto_cookies(force_refresh=False)

                    if new_psid and new_ts:
                        gemini_client = GeminiClient(new_psid, new_ts)
                        await gemini_client.init(auto_refresh=False)
                        # 注意：这里不急着重置 auth_failure_count，等发送成功了再重置
                        # 但如果是首次初始化成功，可以认为是健康的
                        if auth_failure_count < 100:
                            auth_failure_count = 0
                    else:
                        raise Exception("No cookies found during init")
                except Exception as e:
                    # 初始化失败，计数器 +1 (如果是 429 状态，保持 100+; 普通状态 +1)
                    if auth_failure_count < 100:
                        auth_failure_count += 1
                    last_auth_failure_time = time.time()
                    raise HTTPException(status_code=500, detail="Gemini client init failed")
            else:
                debug_log("❄️ 冷却时间已过，尝试解除熔断...", "INFO")

        # =================================================================
        # --- 1. 获取或创建对话 ---
        # =================================================================
        chat = None
        is_recovered_session = False
        if conversation_id:
            if conversation_id in active_chats:
                chat = active_chats[conversation_id]
                is_recovered_session = True
                debug_log("使用内存中的对话", "CHAT")
            else:
                metadata = load_conversation(conversation_id)
                if metadata:
                    chat = gemini_client.start_chat(metadata=metadata, model=model)
                    active_chats[conversation_id] = chat
                    is_recovered_session = True
                    debug_log("从文件恢复对话", "CHAT")

        if chat is None:
            if not conversation_id:
                conversation_id = str(uuid.uuid4())
            chat = gemini_client.start_chat(model=model)
            active_chats[conversation_id] = chat
            debug_log(f"初始化新会话: {conversation_id}", "CHAT")

        # =================================================================
        # --- 3. 构建最终 Prompt (上下文注入逻辑) ---
        # =================================================================
        final_prompt = current_msg_content

        # 🔥 判定逻辑：
        # 如果这不是一个本地恢复的会话 (是新开的)，并且请求里包含了历史记录 (>1条)
        # 说明发生了【节点漂移】，我们需要手动把历史记忆注入进去！
        if (not is_recovered_session) and (len(all_messages) > 1):
            recent_messages = all_messages[-11:-1]
            history_len = len(recent_messages)
            debug_log(f"🔄 检测到节点漂移，正在注入最近 {history_len} 条历史记录...", "WARNING")

            # 构建“剧本式”上下文
            context_str = "Here is the conversation history so far for context:\n\n"
            for msg in recent_messages:
                role_label = "User" if msg.role == "user" else "Model"
                context_str += f"[{role_label}]: {msg.content}\n"

            context_str += "\n[System]: Please continue the conversation based on the history above.\n"
            context_str += f"\n[User]: {current_msg_content}"

            final_prompt = context_str

        # =================================================================
        # --- 2. 发送消息 (核心逻辑) ---
        # =================================================================
        debug_log("正在发送消息到 Gemini...", "REQUEST")
        start_time = time.time()
        response = None

        try:
            if files:
                response = await chat.send_message(current_msg_content, files=files)
            else:
                response = await chat.send_message(final_prompt)

            # ✅ 成功！重置所有故障计数器
            if auth_failure_count > 0:
                debug_log("✅ 调用成功，系统恢复健康，重置熔断计数器。", "SUCCESS")
                auth_failure_count = 0

        except Exception as first_e:
            # 捕获异常，转为小写字符串方便判断
            error_str = str(first_e).lower()
            current_time = time.time()

            # -----------------------------------------------------
            # 🛑 策略 A: 针对 429 限流 (必杀逻辑)
            # -----------------------------------------------------
            if "429" in error_str:
                debug_log(f"💀 严重警告: 触发 Google 429 限流! {first_e}", "ERROR")

                # 直接将计数器设为 100，触发 CRITICAL_COOL_DOWN (1小时)
                auth_failure_count = 100
                last_auth_failure_time = current_time

                # ❌ 绝对不要重试，直接报错
                raise HTTPException(
                    status_code=429,
                    detail="Upstream service rate limited (429). System entering deep freeze for 1 hour."
                )

            # -----------------------------------------------------
            # 🔄 策略 B: 针对常规认证失效 (尝试救活)
            # -----------------------------------------------------
            is_auth_error = (
                    "401" in error_str or
                    "403" in error_str or
                    "cookie" in error_str or
                    "unauthenticated" in error_str or
                    "invalid response" in error_str or
                    "failed to generate" in error_str or
                    "server disconnected" in error_str or
                    "remoteprotocolerror" in error_str or
                    "connection closed" in error_str
            )

            if is_auth_error:
                debug_log(f"⚠️ 认证失效 ({first_e})，准备尝试刷新 Cookie...", "WARNING")

                try:
                    # --- 尝试 1: 强制刷新 Cookie (Force Refresh) ---
                    # 只有在非 429 错误时，才敢去浏览器抓新 Cookie
                    new_psid, new_ts = get_auto_cookies(force_refresh=True)

                    if not new_psid or not new_ts:
                        raise Exception("浏览器中未找到有效 Cookie")

                    debug_log("✅ 抓取到新 Cookie，正在重置客户端...", "INFO")

                    # 重置客户端
                    gemini_client = GeminiClient(new_psid, new_ts)
                    await gemini_client.init(auto_refresh=False)

                    # 重建会话 (尝试保留上下文)
                    if conversation_id in active_chats:
                        old_chat = active_chats[conversation_id]
                        # 尝试用新的 client 恢复旧的 session
                        chat = gemini_client.start_chat(metadata=old_chat.metadata, model=model)
                    else:
                        chat = gemini_client.start_chat(model=model)

                    active_chats[conversation_id] = chat

                    # --- 尝试 2: 立即重试发送 ---
                    debug_log("🔄 Cookie 刷新成功，正在重试请求...", "REQUEST")
                    if files:
                        response = await chat.send_message(current_msg_content, files=files)
                    else:
                        response = await chat.send_message(final_prompt)

                    debug_log("✅ 重试成功，危机解除！", "SUCCESS")
                    auth_failure_count = 0  # 成功后归零

                except Exception as retry_e:
                    # 重试依然失败 -> 计数器 +1
                    if auth_failure_count < 100:
                        auth_failure_count += 1

                    last_auth_failure_time = current_time
                    debug_log(f"❌ 重试失败 (当前失败次数: {auth_failure_count}): {retry_e}", "ERROR")

                    raise HTTPException(
                        status_code=401,
                        detail=f"Session expired and recover failed. Failure count: {auth_failure_count}"
                    )
            else:
                # 其他未知错误 (如网络中断、参数错误等)，直接抛出，不触发熔断
                debug_log(f"❌ 未知错误: {first_e}", "ERROR")
                raise first_e

        # =================================================================
        # --- 3. 处理响应 ---
        # =================================================================
        elapsed_time = time.time() - start_time
        debug_log(f"收到响应 (耗时: {elapsed_time:.2f}s)", "RESPONSE")

        content = response.text or ""
        save_conversation(conversation_id, chat.metadata)

        if response.images:
            debug_log(f"响应包含 {len(response.images)} 张图片", "IMAGE")
            base_url = f"{req.url.scheme}://{req.headers.get('host', req.client.host)}"
            content += "\n\n**生成的图片：**\n"
            today_dir = get_today_dir()

            for idx, img in enumerate(response.images, 1):
                filename = generate_filename()
                success = await img.save(path=str(today_dir), filename=f"{filename}.png")
                if success:
                    saved_file = today_dir / f"{filename}.png"
                    relative_path = saved_file.relative_to(IMAGES_BASE_DIR)
                    image_url = f"{base_url}/images/{relative_path.as_posix()}"
                    content += f"\n![Image {idx}]({image_url})"

        return {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model,
            "conversation_id": conversation_id,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop"
            }]
        }

    except HTTPException:
        raise
    except Exception as e:
        debug_log(f"请求失败: {type(e).__name__}: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    try:
        debug_log(f"收到文件上传: {len(files)} 个", "FILE")
        uploaded_paths = []
        for file in files:
            file_path = UPLOADS_DIR / f"{generate_filename()}_{file.filename}"
            content = await file.read()
            with open(file_path, 'wb') as f:
                f.write(content)
            uploaded_paths.append(str(file_path))
        return {"success": True, "files": uploaded_paths}
    except Exception as e:
        debug_log(f"上传失败: {e}", "ERROR")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversations")
async def list_conversations():
    conversations = []
    for file_path in CONVERSATIONS_DIR.glob("*.json"):
        stat = file_path.stat()
        conversations.append({
            "conversation_id": file_path.stem,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "size_kb": round(stat.st_size / 1024, 2)
        })
    conversations.sort(key=lambda x: x['modified'], reverse=True)
    return {"total": len(conversations), "conversations": conversations}


@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    metadata = load_conversation(conversation_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation_id": conversation_id, "metadata": metadata}


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    if conversation_id in active_chats:
        del active_chats[conversation_id]
    file_path = CONVERSATIONS_DIR / f"{conversation_id}.json"
    if file_path.exists():
        file_path.unlink()
        return {"message": "Conversation deleted"}
    raise HTTPException(status_code=404, detail="Conversation not found")


@app.get("/images/{year_month}/{date}/{filename}")
async def get_image(year_month: str, date: str, filename: str):
    file_path = IMAGES_BASE_DIR / year_month / date / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(str(file_path.absolute()), media_type="image/png")


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [{"id": name, "object": "model", "owned_by": "google"} for name in MODEL_MAP.keys()]
    }


@app.get("/health")
async def health():
    images = list(IMAGES_BASE_DIR.rglob("*.png"))
    conversations = list(CONVERSATIONS_DIR.glob("*.json"))
    return {
        "status": "ok",
        "storage": {
            "total_images": len(images)
        },
        "conversations": {
            "total": len(conversations),
            "active_in_memory": len(active_chats)
        }
    }


if __name__ == "__main__":
    import uvicorn

    debug_log("🚀 启动 Gemini Chat 服务器", "INFO")
    uvicorn.run("server:app", host=HOST, port=PORT, reload=True)