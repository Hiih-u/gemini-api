import os
import time
import uuid
import secrets
import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
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

# 配置
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
IMAGES_BASE_DIR = Path(os.getenv("IMAGES_DIR", "stored_images"))
IMAGES_BASE_DIR.mkdir(exist_ok=True)

CONVERSATIONS_DIR = Path("conversations")
CONVERSATIONS_DIR.mkdir(exist_ok=True)

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)

STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)

gemini_client = None
active_chats = {}

DEBUG = os.getenv("DEBUG", "true").lower() == "true"

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


def get_auto_cookies():
    """尝试从浏览器自动获取 Gemini Cookie"""
    if not browser_cookie3:
        debug_log("未安装 browser_cookie3，跳过自动获取", "WARNING")
        return None, None

    debug_log("正在尝试从 Kasm Chrome 自动获取 Cookie...", "INFO")
    try:
        # 这里对应你刚才测试成功的代码
        cj = browser_cookie3.chrome(domain_name='.google.com')
        psid = None
        ts = None

        for cookie in cj:
            if cookie.name == '__Secure-1PSID':
                psid = cookie.value
            if cookie.name == '__Secure-1PSIDTS':
                ts = cookie.value

        if psid and ts:
            debug_log(f"✅ 自动获取成功! TS: {ts[:10]}...", "SUCCESS")
            return psid, ts
        else:
            debug_log("❌ 浏览器数据库读取成功，但未找到 Gemini Cookie (请确认已登录)", "WARNING")
            return None, None
    except Exception as e:
        debug_log(f"❌ 自动获取失败: {e}", "ERROR")
        return None, None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global gemini_client

    # 1. 优先从环境变量读取
    secure_1psid = os.getenv("SECURE_1PSID")
    secure_1psidts = os.getenv("SECURE_1PSIDTS")

    # 2. 如果环境变量缺失，尝试自动获取
    if not secure_1psid or not secure_1psidts:
        debug_log("环境变量未配置 Cookie，尝试自动获取...", "INFO")
        auto_psid, auto_ts = get_auto_cookies()
        if auto_psid and auto_ts:
            secure_1psid = auto_psid
            secure_1psidts = auto_ts

    debug_log("开始初始化 Gemini 客户端...", "INFO")
    try:
        # 使用最终获取到的 Cookie 初始化
        if not secure_1psid or not secure_1psidts:
            raise ValueError("无法获取有效的 Cookie (环境变量为空且自动获取失败)")

        gemini_client = GeminiClient(secure_1psid, secure_1psidts)
        await gemini_client.init(auto_refresh=True)
        debug_log("Gemini 客户端初始化成功", "SUCCESS")

        # 打印目录信息
        debug_log(f"图片存储目录: {IMAGES_BASE_DIR.absolute()}", "INFO")
        debug_log(f"对话历史目录: {CONVERSATIONS_DIR.absolute()}", "INFO")

    except Exception as e:
        debug_log(f"初始化失败: {e}", "ERROR")
        # 这里不 raise，防止整个服务起不来，可以在调用接口时再报错
        # raise
    yield

app = FastAPI(lifespan=lifespan, title="Gemini Chat API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: List[Message]
    conversation_id: Optional[str] = None
    files: Optional[List[str]] = None  # 文件路径列表


MODEL_MAP = {
    "gemini-pro": Model.G_2_5_PRO,
    "gemini-2.5-pro": Model.G_2_5_PRO,
    "gemini-2.5-flash": Model.G_2_5_FLASH,
    "gemini-3.0-pro": Model.G_3_0_PRO,
    "default": Model.UNSPECIFIED,
}


def get_today_dir() -> Path:
    """获取今天的图片目录：年月/日期"""
    now = datetime.now()
    year_month = now.strftime("%Y%m")
    date = now.strftime("%Y%m%d")
    dir_path = IMAGES_BASE_DIR / year_month / date
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def generate_filename() -> str:
    """生成文件名：年月日时分秒_随机数"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_suffix = secrets.token_hex(4)
    return f"{timestamp}_{random_suffix}"


def save_conversation(conversation_id: str, metadata: dict):
    """保存对话历史"""
    file_path = CONVERSATIONS_DIR / f"{conversation_id}.json"
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    debug_log(f"对话已保存: {conversation_id}", "CHAT")


def load_conversation(conversation_id: str) -> Optional[dict]:
    """加载对话历史"""
    file_path = CONVERSATIONS_DIR / f"{conversation_id}.json"
    if file_path.exists():
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


@app.get("/", response_class=HTMLResponse)
async def root():
    """返回前端页面"""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    else:
        return """
        <html>
            <head><title>Gemini Chat</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1>⚠️ 前端页面未找到</h1>
                <p>请在 <code>static/index.html</code> 创建前端页面</p>
                <p>或访问 <a href="/docs">API 文档</a></p>
            </body>
        </html>
        """


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest, req: Request):
    """
    OpenAI 兼容接口 (增强版：支持 Cookie 失效自动重连)

    支持：
    1. 纯文本对话
    2. 带文件的对话（files 参数传递文件路径）
    3. 对话历史（conversation_id）
    4. 自动处理 401/403 认证失效并重试
    """
    global gemini_client  # 关键：需要修改全局客户端对象

    try:
        user_message = request.messages[-1].content
        model = MODEL_MAP.get(request.model, Model.UNSPECIFIED)
        conversation_id = request.conversation_id
        files = request.files

        debug_log("=" * 60, "REQUEST")
        debug_log(f"模型: {request.model}", "REQUEST")
        debug_log(f"对话ID: {conversation_id or '新对话'}", "REQUEST")
        debug_log(f"消息: {user_message[:100]}{'...' if len(user_message) > 100 else ''}", "REQUEST")
        if files:
            debug_log(f"包含文件: {len(files)} 个", "FILE")

        # --- 1. 获取或创建对话 ---
        chat = None
        if conversation_id:
            if conversation_id in active_chats:
                chat = active_chats[conversation_id]
                debug_log("使用内存中的对话", "CHAT")
            else:
                metadata = load_conversation(conversation_id)
                if metadata:
                    chat = gemini_client.start_chat(metadata=metadata, model=model)
                    active_chats[conversation_id] = chat
                    debug_log("从文件恢复对话", "CHAT")

        if chat is None:
            if not conversation_id:
                conversation_id = str(uuid.uuid4())
            # 如果是新对话，直接开始
            chat = gemini_client.start_chat(model=model)
            active_chats[conversation_id] = chat
            debug_log(f"初始化新会话: {conversation_id}", "CHAT")

        # --- 2. 发送消息 (带失效重试逻辑) ---
        debug_log("正在发送消息到 Gemini...", "REQUEST")
        start_time = time.time()
        response = None

        try:
            # 第一次尝试发送
            if files:
                response = await chat.send_message(user_message, files=files)
            else:
                response = await chat.send_message(user_message)

        except Exception as first_e:
            # 捕获异常，分析是否为认证失效
            error_str = str(first_e).lower()
            is_auth_error = "401" in error_str or "403" in error_str or "cookie" in error_str or "unauthenticated" in error_str

            if is_auth_error:
                debug_log(f"⚠️ 认证失效 ({first_e})，正在尝试自动续期...", "WARNING")

                # A. 重新从浏览器数据库读取 Cookie
                new_psid, new_ts = get_auto_cookies()

                if new_psid and new_ts:
                    debug_log("✅ 成功从浏览器获取新 Cookie，正在重置客户端...", "INFO")

                    # B. 重新初始化全局客户端
                    gemini_client = GeminiClient(new_psid, new_ts)
                    await gemini_client.init(auto_refresh=True)

                    # C. 重建对话对象 (必须！旧对象已废弃)
                    # 如果有历史记录，尝试恢复上下文
                    metadata = load_conversation(conversation_id)
                    if metadata:
                        chat = gemini_client.start_chat(metadata=metadata, model=model)
                    else:
                        chat = gemini_client.start_chat(model=model)

                    # 更新缓存
                    active_chats[conversation_id] = chat

                    # D. 再次尝试发送 (重试)
                    debug_log("🔄 正在重试发送消息...", "REQUEST")
                    if files:
                        response = await chat.send_message(user_message, files=files)
                    else:
                        response = await chat.send_message(user_message)

                    debug_log("✅ 重试成功！", "SUCCESS")
                else:
                    # 获取不到 Cookie，彻底失败
                    debug_log("❌ 无法自动获取 Cookie，请检查 Kasm 桌面是否已登录 Google", "ERROR")
                    raise HTTPException(status_code=401,
                                        detail="Session expired. Please login to Google in Kasm desktop.")
            else:
                # 如果不是认证错误（比如网络超时、参数错误），直接抛出，不重试
                raise first_e

        # --- 3. 处理响应 ---
        elapsed_time = time.time() - start_time
        debug_log(f"收到响应 (耗时: {elapsed_time:.2f}s)", "RESPONSE")

        content = response.text or ""

        # 保存对话历史
        save_conversation(conversation_id, chat.metadata)

        # 处理图片
        if response.images:
            debug_log(f"响应包含 {len(response.images)} 张图片", "IMAGE")
            base_url = f"{req.url.scheme}://{req.headers.get('host', req.client.host)}"
            content += "\n\n**生成的图片：**\n"
            today_dir = get_today_dir()

            for idx, img in enumerate(response.images, 1):
                filename = generate_filename()
                success = await img.save(
                    path=str(today_dir),
                    filename=f"{filename}.png"
                )
                if success:
                    saved_file = today_dir / f"{filename}.png"
                    if saved_file.exists():
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
                "message": {
                    "role": "assistant",
                    "content": content
                },
                "finish_reason": "stop"
            }]
        }

    except HTTPException:
        raise
    except Exception as e:
        debug_log(f"请求失败: {type(e).__name__}: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        # 统一返回 500
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """
    文件上传接口
    返回上传文件的路径，供后续聊天使用
    """
    try:
        debug_log(f"收到文件上传: {len(files)} 个", "FILE")

        uploaded_paths = []
        for file in files:
            file_path = UPLOADS_DIR / f"{generate_filename()}_{file.filename}"
            content = await file.read()

            with open(file_path, 'wb') as f:
                f.write(content)

            uploaded_paths.append(str(file_path))
            debug_log(f"文件已保存: {file.filename}", "SUCCESS")

        return {
            "success": True,
            "files": uploaded_paths,
            "count": len(uploaded_paths)
        }

    except Exception as e:
        debug_log(f"上传失败: {e}", "ERROR")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversations")
async def list_conversations():
    """列出所有对话"""
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
    """获取对话详情"""
    metadata = load_conversation(conversation_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation_id": conversation_id, "metadata": metadata}


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """删除对话"""
    if conversation_id in active_chats:
        del active_chats[conversation_id]

    file_path = CONVERSATIONS_DIR / f"{conversation_id}.json"
    if file_path.exists():
        file_path.unlink()
        return {"message": "Conversation deleted"}

    raise HTTPException(status_code=404, detail="Conversation not found")


@app.get("/images/{year_month}/{date}/{filename}")
async def get_image(year_month: str, date: str, filename: str):
    """返回图片"""
    file_path = IMAGES_BASE_DIR / year_month / date / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(str(file_path.absolute()), media_type="image/png")


@app.get("/v1/models")
async def list_models():
    """列出模型"""
    return {
        "object": "list",
        "data": [
            {"id": name, "object": "model", "owned_by": "google"}
            for name in MODEL_MAP.keys()
        ]
    }


@app.get("/health")
async def health():
    """健康检查"""
    images = list(IMAGES_BASE_DIR.rglob("*.jpg"))
    images.extend(IMAGES_BASE_DIR.rglob("*.png"))
    total_size = sum(f.stat().st_size for f in images if f.is_file())
    conversations = list(CONVERSATIONS_DIR.glob("*.json"))
    uploads = list(UPLOADS_DIR.glob("*"))

    return {
        "status": "ok",
        "storage": {
            "images_directory": str(IMAGES_BASE_DIR.absolute()),
            "total_images": len(images),
            "total_size_mb": round(total_size / 1024 / 1024, 2)
        },
        "conversations": {
            "directory": str(CONVERSATIONS_DIR.absolute()),
            "total": len(conversations),
            "active_in_memory": len(active_chats)
        },
        "uploads": {
            "directory": str(UPLOADS_DIR.absolute()),
            "total_files": len(uploads)
        }
    }


if __name__ == "__main__":
    import uvicorn

    debug_log("=" * 60, "INFO")
    debug_log("🚀 启动 Gemini Chat 服务器", "INFO")
    debug_log(f"📍 地址: http://{HOST}:{PORT}", "INFO")
    debug_log(f"📚 API 文档: http://{HOST}:{PORT}/docs", "INFO")
    debug_log(f"🎨 前端页面: http://{HOST}:{PORT}/", "INFO")
    debug_log("=" * 60, "INFO")

    uvicorn.run("server:app", host=HOST, port=PORT, reload=True)
