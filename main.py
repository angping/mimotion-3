# -*- coding: utf8 -*-
import datetime
import json
import math
import random
import re
import sys
import time
import pytz

import requests

# 开启根据地区天气情况降低步数（默认关闭）
# To enable weather-based step reduction, set the third command-line argument to "True"
open_get_weather = sys.argv[3]
# 设置获取天气的地区（上面开启后必填）如：area = "宁波"
# Set the area for weather checking (required if the above is enabled), e.g., area = "Ningbo"
area = sys.argv[4]

# 以下如果看不懂直接默认就行只需改上面
# The following can be left as default if you are unsure.

# 系数K查询到天气后降低步数比率，如查询得到设置地区为多云天气就会在随机后的步数乘0.9作为最终修改提交的步数
# K_dict defines the step reduction ratio based on weather conditions.
K_dict = {"多云": 0.9, "阴": 0.8, "小雨": 0.7, "中雨": 0.5, "大雨": 0.4, "暴雨": 0.3, "大暴雨": 0.2, "特大暴雨": 0.2}

# 北京时间
# Get current time in Beijing timezone
time_bj = datetime.datetime.now(pytz.timezone('Asia/Shanghai'))
now = time_bj.strftime("%Y-%m-%d %H:%M:%S")

# Modernized headers based on recent app versions
headers = {
    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
    "User-Agent": "MiFit/6.12.0 (MCE16; Android 16; Density/1.5)",
    "app_name": "com.xiaomi.hm.health",
}


# 获取区域天气情况
def getWeather():
    """Fetches weather for the specified area and sets the reduction factor K."""
    if area == "NO":
        print("Weather check is disabled as area is set to NO.")
        return
    else:
        global K, type
        url = 'http://wthrcdn.etouch.cn/weather_mini?city=' + area
        try:
            r = requests.get(url=url, headers={'User-Agent': 'Mozilla/5.0'})
            r.raise_for_status()  # Raise an exception for bad status codes
            res = r.json()
            weather_type = res['data']['forecast'][0]['type']
            type = weather_type # Store the weather type for logging
            for condition, factor in K_dict.items():
                if condition in weather_type:
                    K = factor
                    break
        except requests.exceptions.RequestException as e:
            print(f"获取天气情况出错 (Error fetching weather): {e}")
        except (KeyError, json.JSONDecodeError):
            print("解析天气数据失败 (Failed to parse weather data).")


# 获取北京时间确定随机步数&启动主函数
def getBeijinTime():
    """
    Main orchestrator. Determines step range based on time of day,
    optionally adjusts for weather, and initiates the step submission process.
    """
    global K, type
    K = 1.0
    type = ""
    if open_get_weather.lower() == "true":
        getWeather()

    # Use current hour from a reliable source (local system time in BJ timezone)
    hour = time_bj.hour
    min_ratio = max(math.ceil((int(hour) / 3) - 1), 0)
    max_ratio = math.ceil(int(hour) / 3)
    min_1 = 3500 * min_ratio
    max_1 = 3500 * max_ratio
    min_1 = int(K * min_1)
    max_1 = int(K * max_1)

    if min_1 < max_1:
        user_mi = sys.argv[1]
        passwd_mi = sys.argv[2]
        user_list = user_mi.split('#')
        passwd_list = passwd_mi.split('#')

        if len(user_list) == len(passwd_list):
            msg_mi = ""
            if K != 1.0:
                msg_mi = f"由于天气 (Weather is) {type}，已设置降低步数, 系数为 (step count reduced by factor) {K}。\n"
            
            for user_mi, passwd_mi in zip(user_list, passwd_list):
                msg_mi += main(user_mi, passwd_mi, min_1, max_1)
        else:
            print("用户名和密码数量不匹配 (Number of users and passwords do not match).")
    else:
        print(f"[{now}] 当前时间段计算的步数范围为0，不提交 (Step range calculated for the current time is 0, skipping submission).")
        return


def login(user, password):
    """
    Handles user login for both phone numbers and emails, returning necessary tokens.
    This function is adapted from the zepplife.py script for compatibility.
    """
    is_phone = bool(re.match(r'^\d{11}$', user))
    
    login_url = ""
    third_name = ""
    login_user = user

    if is_phone:
        login_user = f"+86{user}"
        login_url = f"https://api-user.huami.com/registrations/{login_user}/tokens"
        third_name = "huami_phone"
    else:
        login_url = f"https://api-user.huami.com/registrations/{user}/tokens"
        third_name = "huami"

    login_data = {
        "client_id": "HuaMi",
        "password": password,
        "redirect_uri": "https://s3-us-west-2.amazonaws.com/hm-registration/successsignin.html",
        "token": "access",
        "country_code": "CN",
        "json_response": "true",
        "name": login_user,
    }

    try:
        # Step 1: Get Access Code
        r1 = requests.post(login_url, data=login_data, headers=headers)
        
        if r1.status_code == 429:
             print("登录失败: 请求过于频繁，请变更IP或稍后再试 (Login failed: Too many requests, change IP or try again later).")
             return None
        
        r1.raise_for_status()
        res1_json = r1.json()

        if "access" not in res1_json:
            print(f"登录失败: 用户名或密码错误，请检查。 响应: {res1_json}")
            return None
        code = res1_json["access"]

        # Step 2: Exchange Access Code for Login/App Tokens
        token_url = "https://account.huami.com/v2/client/login"
        token_data = {
            "app_name": "com.xiaomi.hm.health",
            "app_version": "6.12.0",
            "code": code,
            "country_code": "CN",
            "device_id": "02:00:00:00:00:00", # Generic device ID
            "device_model": "android_phone",
            "grant_type": "access_token",
            "third_name": third_name,
            "allow_registration": "false",
            "source": "com.xiaomi.hm.health",
        }
        
        r2 = requests.post(token_url, data=token_data, headers=headers)
        r2.raise_for_status()
        res2_json = r2.json()

        if "token_info" in res2_json:
            return {
                "user_id": res2_json["token_info"]["user_id"],
                "app_token": res2_json["token_info"]["app_token"]
            }
        else:
            print(f"登录失败: 未能获取token_info. 响应: {res2_json}")
            return None

    except requests.exceptions.HTTPError as e:
        print(f"登录失败: HTTP Error {e.response.status_code}. 响应: {e.response.text}")
        return None
    except Exception as e:
        print(f"登录时发生未知错误 (An unknown error occurred during login): {e}")
        return None


# 主函数
def main(_user, _passwd, min_1, max_1):
    """
    Main function to submit step count for a single user.
    """
    user = str(_user)
    password = str(_passwd)
    step = str(random.randint(min_1, max_1))
    print(f"用户(User): {user} | 准备提交步数 (Preparing to submit steps): {step} (范围 Range: {min_1}~{max_1})")

    if not user or not password:
        print("用户名或密码为空 (Username or password is empty)!")
        return "Username or password empty!"

    token_info = login(user, password)
    if not token_info:
        # Obscure phone number for privacy in logs
        display_user = f"{user[:3]}****{user[7:]}" if len(user) == 11 and user.isdigit() else user
        result_msg = f"[{now}]\n账号 (Account)：{display_user}\n修改步数 (Modify steps)（{step}）[Login Fail!]\n"
        print(result_msg)
        return result_msg

    userid = token_info['user_id']
    app_token = token_info['app_token']
    
    t_millis_str = get_time_str()
    t_seconds = int(int(t_millis_str) / 1000)
    today = time_bj.strftime("%F")
    
    # This is a sample data structure. The content inside 'data_hr' and 'stage' is largely boilerplate.
    # The key is to replace the date, seconds, and the total step count.
    device_id = "88CC5224060006C4" # A sample device ID
    data_json_template = (
        f'%5B%7B%22data_hr%22%3A%22%22%2C%22date%22%3A%22{today}%22%2C'
        f'%22last_sync_time%22%3A{t_seconds}%2C%22device_id%22%3A%22{device_id}%22%2C'
        f'%22tz%22%3A32%2C%22did%22%3A%22{device_id}%22%2C%22src%22%3A24%7D%5D'
    )
    summary_template = (
        f'%7B%22v%22%3A6%2C%5C%22slp%5C%22%3A%7B%5C%22st%5C%22%3A{t_seconds}%2C%5C%22ed%5C%22%3A{t_seconds}%2C%5C%22dp%5C%22%3A0%2C%5C%22lt%5C%22%3A0%2C%5C%22wk%5C%22%3A0%2C%5C%22usrSt%5C%22%3A-1440%2C%5C%22usrEd%5C%22%3A-1440%2C%5C%22wc%5C%22%3A0%2C%5C%22is%5C%22%3A0%2C%5C%22lb%5C%22%3A0%2C%5C%22to%5C%22%3A0%2C%5C%22dt%5C%22%3A0%2C%5C%22rhr%5C%22%3A0%2C%5C%22ss%5C%22%3A0%7D%2C'
        f'%5C%22stp%5C%22%3A%7B%5C%22ttl%5C%22%3A{step}%2C%5C%22dis%5C%22%3A10627%2C%5C%22cal%5C%22%3A510%2C%5C%22wk%5C%22%3A41%2C%5C%22rn%5C%22%3A50%2C%5C%22runDist%5C%22%3A7654%2C%5C%22runCal%5C%22%3A397%7D%2C'
        f'%5C%22goal%5C%22%3A8000%2C%5C%22tz%5C%22%3A%5C%2228800%5C%22%7D'
    )
    
    data_json_full = data_json_template.replace('data%22%3A%5B%5D', f'data%22%3A%5B%5D%2C%22summary%22%3A%22{summary_template}%22')

    url = f'https://api-mifit-cn.huami.com/v1/data/band_data.json?&t={t_millis_str}'
    
    submission_headers = headers.copy()
    submission_headers["apptoken"] = app_token
    
    data = f'userid={userid}&last_sync_data_time={t_seconds}&device_type=0&last_deviceid={device_id}&data_json={data_json_full}'

    try:
        response = requests.post(url, data=data, headers=submission_headers).json()
        message = response.get('message', 'No message field in response')
    except Exception as e:
        message = f"Submission Error: {e}"

    display_user = f"{user[:3]}****{user[7:]}" if len(user) == 11 and user.isdigit() else user
    result = f"[{now}]\n账号 (Account)：{display_user}\n修改步数 (Modify steps)（{step}）[{message}]\n"
    print(result)
    return result


def get_time_str():
    """Returns the current timestamp in milliseconds as a string for the Asia/Shanghai timezone."""
    utc_now = datetime.datetime.utcnow()
    beijing_tz = pytz.timezone('Asia/Shanghai')
    beijing_now = utc_now.replace(tzinfo=pytz.utc).astimezone(beijing_tz)
    return str(int(beijing_now.timestamp() * 1000))


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python main.py <users> <passwords> <use_weather_bool> <area>")
        print("Example for one user: python main.py 'your_email@example.com' 'your_password' 'False' 'NO'")
        print("Example for multiple users: python main.py 'user1@email.com#13800138000' 'pass1#pass2' 'True' '北京'")
        print("Note: Users and passwords are separated by '#'. <area> is 'NO' if weather is False.")
        sys.exit(1)
    getBeijinTime()
