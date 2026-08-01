import urllib.parse
import re
import requests
from playwright.sync_api import sync_playwright

# 浏览器登录获取pc_token + 导出登录后的Cookie用于请求
def get_pc_token():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://zuoye.xinkaoyun.com/#/user/login")
        print("\n==============================")
        print("浏览器已打开，请手动完成登录！")
        print("登录成功、进入主页后，回到终端按回车")
        print("==============================")
        input("登录完成后按回车继续：")
        # 获取localStorage token
        storage_text = page.evaluate("() => JSON.stringify(localStorage)")
        match_res = re.search(r'(pc_\w+)', storage_text)
        pc_token = match_res.group(1) if match_res else None
        # 导出登录Cookie，给requests使用
        cookies = page.context.cookies()
        browser.close()
        cookie_dict = {}
        for ck in cookies:
            cookie_dict[ck["name"]] = ck["value"]
        return pc_token, cookie_dict

# 获取对应sid下的作业列表
def fetch_task_data(token, sid, cookie_dict):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://zuoye.xinkaoyun.com/"
    }
    api_params = {
        "page": 1,
        "limit": 99999999,
        "sid": sid,
        "start": "2026-07-01",
        "end": "2026-08-31",
        "token": token
    }
    url = "https://zuoyenew.xinkaoyun.com:30001/holidaywork/student/getMutualTasks"
    try:
        response = requests.get(url, params=api_params, headers=headers, cookies=cookie_dict, timeout=12)
        res_json = response.json()
        # 识别登录超时/异地登录
        if res_json.get("state") == "over":
            print(f"sid={sid} 账号状态异常：{res_json.get('msg')}")
        return res_json
    except requests.exceptions.RequestException as err:
        print(f"sid={sid} 接口请求异常：{err}")
        return None
    except ValueError:
        print(f"sid={sid} 返回数据解析失败，非标准JSON格式")
        return None

# 请求排名接口【核心修复：Cookie、正确字段名、兼容state=ok】
def fetch_rank_info(taskId, token, rank_type, cookie_dict):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://zuoye.xinkaoyun.com/"
    }
    base = "https://zuoyenew.xinkaoyun.com:30001/holidaywork/student/"
    if rank_type == "C":
        api_url = base + "getClassRanks"
        print("\n【班级排名接口】")
    else:
        api_url = base + "getGradeRanks"
        print("\n【年级排名接口】")

    params = {
        "page": 1,
        "limit": 99999999,
        "taskId": taskId,
        "token": token
    }
    full_url = f"{api_url}?{urllib.parse.urlencode(params)}"
    print(f"完整请求链接：{full_url}")
    try:
        # 带上登录Cookie，和浏览器环境保持一致
        resp = requests.get(api_url, params=params, headers=headers, cookies=cookie_dict, timeout=12)
        data = resp.json()
        # 打印原始JSON用于调试，可注释
        # print("原始接口返回：", data)

        # 兼容接口state=ok的成功标识，不再判断code
        if data.get("state") == "over":
            print(f"账号拦截提示：{data.get('msg')}，请重新登录！")
            return
        if data.get("state") != "ok":
            print(f"接口请求失败，state：{data.get('state')}，msg：{data.get('msg','无')}")
            return

        rank_list = data.get("data", [])
        if not rank_list:
            print("该任务暂无任何排名数据！")
            return
        # 加宽列宽，对齐输出
        print("\n{:<15} {:<20} {:<20}".format("userId", "realName", "correctRealName"))
        print("-" * 60)
        for item in rank_list:
            # 严格匹配浏览器返回的字段名：userId / realName / correctRealName
            uid = str(item.get("userId", ""))
            rn = str(item.get("realName", ""))
            crn = str(item.get("correctRealName", ""))
            print("{:<15} {:<20} {:<20}".format(uid, rn, crn))
    except requests.exceptions.RequestException as e:
        print(f"排名接口网络请求失败：{e}")
    except ValueError:
        print("排名接口返回数据不是标准JSON，解析失败")
    except Exception as err:
        print(f"排名接口未知异常：{err}")

# 请求作业详情接口，提取所有30001域名jpg图片链接
def extract_jpg_image_links(task_id, user_id, token, cookie_dict):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://zuoye.xinkaoyun.com/"
    }
    base_api = "https://zuoyenew.xinkaoyun.com:30001/holidaywork/student/getMutualTaskInfo"
    req_params = {"taskId": task_id, "userId": user_id, "token": token}
    detail_url = f"{base_api}?{urllib.parse.urlencode(req_params)}"
    print(f"\n作业详情接口地址：{detail_url}")
    try:
        resp = requests.get(base_api, params=req_params, headers=headers, cookies=cookie_dict, timeout=12)
        data = resp.json()
        # 捕获登录超时/异地登录
        if data.get("state") == "over":
            print(f"详情接口账号异常：{data.get('msg')}，请重新登录获取token")
            return []
    except requests.exceptions.RequestException as e:
        print(f"作业详情接口请求失败：{e}")
        return []
    except ValueError:
        print("作业详情返回数据JSON解析失败")
        return []

    # 修复正则：同时匹配 zuoye.xinkaoyun.com 和 zuoyenew.xinkaoyun.com 图片域名
    img_reg = re.compile(r'https://zuoye(?:new)?\.xinkaoyun\.com:30001/\S*?\.jpg', re.IGNORECASE)
    all_content = str(data)
    img_list = img_reg.findall(all_content)

    # 方案2：单独遍历images数组兜底提取
    try:
        for item in data.get("data", []):
            img_arr = item.get("images", [])
            for img_url in img_arr:
                if img_url.endswith(".jpg") and ".xinkaoyun.com:30001" in img_url:
                    img_list.append(img_url)
    except Exception:
        pass

    # 去重
    unique_img = list(dict.fromkeys(img_list))
    return unique_img

def main():
    print("=" * 60)
    print("小鑫作业全年级主观题提取工具v3.8【Powered By Wang Huiyu】")
    print("登录→输出全学科task清单→输入taskId→选择C/G查看排名→输入userId→提取jpg图片链接")
    print("=" * 60)
    # sid与学科对应关系
    subject_map = {1: "语文", 2: "数学", 3: "英语", 4: "历史", 6: "政治", 9: "物理", 10: "化学"}
    sid_arr = [1, 2, 3, 4, 6, 9, 10]

    # 1. 登录获取token + 登录Cookie
    print("\n启动浏览器登录页面，请手动登录账号...")
    token, cookie_dict = get_pc_token()
    if not token:
        print("错误：未读取pc_开头token，程序终止")
        return
    print(f"\n✅ 已获取token：{token}")

    # 2. 遍历全部sid输出作业清单
    print("\n========================================")
    print("正在遍历全部学科，生成taskId对照表")
    print("========================================")
    for sid in sid_arr:
        subject = subject_map[sid]
        print(f"\n----- sid={sid} 【{subject}】 -----")
        task_data = fetch_task_data(token, sid, cookie_dict)
        if not task_data:
            print(f"sid{sid}：内容获取失败")
            continue
        # 异地/超时拦截
        if task_data.get("state") == "over":
            continue
        task_list = task_data.get("data", [])
        if len(task_list) == 0:
            print(f"sid{sid}：暂无作业任务")
            continue
        print(f"sid{sid}【{subject}】任务清单：")
        for idx, item in enumerate(task_list, start=1):
            tid = item.get("taskId")
            task_name = item.get("taskName", item.get("title", "无作业名称"))
            print(f"  序号{idx} | taskId={tid} | 作业名：{task_name}")

    # 循环多次查询图片链接，不自动关闭程序
    while True:
        # 第一步输入taskId
        task_id = input("\n请输入需要操作的taskId：").strip()
        if not task_id:
            print("taskId不能为空，本次跳过")
            opt = input("是否继续查询其他任务(y/N)：").strip().upper()
            if opt != "Y":
                print("程序退出")
                return
            continue

        # 第二步选择C班级排名 / G年级排名
        rank_choice = input("请选择排名类型 按C=ClassRanks班级排名 / 按G=GradeRanks年级排名：").strip().upper()
        if rank_choice in ("C", "G"):
            fetch_rank_info(task_id, token, rank_choice, cookie_dict)
        else:
            print("输入无效，跳过排名查询")

        # 第三步输入userId
        user_id = input("\n请输入userId：").strip()

        # 参数校验
        if not user_id or not token:
            print("参数缺失，本次查询跳过")
            opt = input("是否继续查询其他任务(y/N)：").strip().upper()
            if opt != "Y":
                print("程序退出")
                return
            continue
        if not token.startswith("pc_"):
            print("token格式错误，程序退出")
            return

        # 获取并打印所有jpg图片链接
        jpg_links = extract_jpg_image_links(task_id, user_id, token, cookie_dict)
        print("\n########## 匹配到的JPG图片链接 ##########")
        if len(jpg_links) == 0:
            print("无符合域名要求的.jpg图片链接")
        else:
            for link in jpg_links:
                print(link)
        print("#########################################")

        # 选择是否继续
        select = input("\n是否查询其他task的图片与排名？输入y继续，N退出：").strip().upper()
        if select != "Y":
            print("查询结束，程序关闭")
            return

if __name__ == "__main__":
    main()