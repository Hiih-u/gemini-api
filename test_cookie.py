import browser_cookie3
import requests


def test_google_login():
    try:
        # 尝试从 Chrome 获取 (也可以换成 .edge(), .firefox())
        cj = browser_cookie3.chrome(domain_name='.google.com')

        # 寻找关键 Cookie
        psid = None
        ts = None

        for cookie in cj:
            if cookie.name == '__Secure-1PSID':
                psid = cookie.value
            if cookie.name == '__Secure-1PSIDTS':
                ts = cookie.value

        if psid and ts:
            print("✅ 成功自动获取 Cookie！")
            print(f"Secure_1PSID: {psid[:10]}...")
            print(f"Secure_1PSIDTS: {ts[:10]}...")
            return True
        else:
            print("❌ 读取到了 Cookie 数据库，但没找到 Gemini 的关键 Cookie。请确认浏览器已登录。")
            return False

    except Exception as e:
        print(f"❌ 自动获取失败: {e}")
        return False


if __name__ == "__main__":
    test_google_login()