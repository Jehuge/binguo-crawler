import json
import os

import undetected_chromedriver as uc
from dotenv import load_dotenv
from selenium.webdriver.chrome.service import Service

# 加载环境变量
load_dotenv()

CHROME_BINARY_PATH = os.getenv("CHROME_BINARY_PATH")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH")

def load_driver_with_cookies(start_url="https://www.yiche.com", cookie_file="yiche_cookies.json"):
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")

    if CHROME_BINARY_PATH:
        options.binary_location = CHROME_BINARY_PATH

    service = Service(CHROMEDRIVER_PATH)
    driver = uc.Chrome(
        service=service,
        options=options,
        use_subprocess=True,
        driver_executable_path=CHROMEDRIVER_PATH,  # 显式指定本地 driver
        patcher=False  # 关键：禁用自动联网 patcher
    )
    driver.get(start_url)

    if os.path.exists(cookie_file):
        with open(cookie_file, "r", encoding="utf-8") as f:
            cookies = json.load(f)
            for cookie in cookies:
                if "expiry" in cookie:
                    del cookie["expiry"]
                try:
                    driver.add_cookie(cookie)
                except Exception:
                    pass
        driver.refresh()
        print("✅ 已加载 Yiche Cookies 并刷新页面")
    else:
        print("⚠️ 未找到 yiche_cookies.json，请手动完成验证")
        input("👉 请在浏览器中手动登录或验证，然后按 Enter 继续...")

        cookies = driver.get_cookies()
        with open(cookie_file, "w", encoding="utf-8") as f:
            json.dump(cookies, f)
        print("✅ Yiche Cookies 已保存，下次运行将自动加载")

    return driver