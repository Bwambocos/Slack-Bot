﻿import os
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from bs4 import BeautifulSoup
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
import argparse

sched = BlockingScheduler(
    executors={
        "threadpool": ThreadPoolExecutor(max_workers=5),
        "processpool": ProcessPoolExecutor(max_workers=1),
    }
)

print("ITC-LMS: Bot started")


def init():
    print("init(): started")

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--window-size=1280,1080")
    driver = webdriver.Chrome("/usr/bin/chromedriver", options=options)

    driver.get("https://itc-lms.ecc.u-tokyo.ac.jp/saml/login?disco=true")

    input_id = driver.find_element(By.NAME, "UserName")
    input_password = driver.find_element(By.NAME, "Password")

    input_id.send_keys(os.environ["ITCLMS_ID"])
    input_password.send_keys(os.environ["ITCLMS_PASSWORD"])

    button_login = driver.find_element(By.CLASS_NAME, "submit")
    ActionChains(driver).move_to_element(button_login).perform()
    button_login.click()

    button_yes = driver.find_element(By.ID, "idSIButton9")
    button_yes.click()

    print("init(): done")
    return driver


def getTaskList(driver):
    driver.get("https://itc-lms.ecc.u-tokyo.ac.jp/lms/task")
    soup = BeautifulSoup(driver.page_source, "html.parser")
    tasks = soup.find_all("div", class_="result_list_line")

    taskList = []
    for task in tasks:
        taskList.append(
            {
                "courseName": task.contents[1].text,
                "contents": task.contents[3].contents[1].text,
                "title": task.contents[5].contents[1].text,
                "deadline": task.contents[9].contents[3].text,
                "link": "https://itc-lms.ecc.u-tokyo.ac.jp"
                + task.contents[5].contents[1].attrs["href"],
            }
        )
    return taskList


def getSpecificList(tasks, kind):
    res = []
    for task in tasks:
        if task["contents"] == kind:
            res.append(task)
    return res


def sendMessageToSlack(channel, message, attachments=json.dumps([])):
    try:
        client = WebClient(token=os.environ["SLACK_TOKEN"])
        client.chat_postMessage(channel=channel, text=message, attachments=attachments)
    except Exception as e:
        print("sendMessageToSlack(): " + str(e))
    else:
        print("sendMessageToSlack(): successfully sent message to " + channel)


def sendTasks(tasks):
    message = "未提出の課題: " + str(len(tasks)) + " 件"
    data = []
    for task in tasks:
        data.append(
            {
                "color": "good",
                "title": task["title"],
                "title_link": task["link"],
                "text": "・コース名: " + task["courseName"] + "\n・期限: " + task["deadline"],
            }
        )
    sendMessageToSlack("#itclms-tasks", message, json.dumps(data))


@sched.scheduled_job("cron", minute="0", hour="9, 18", executor="threadpool")
def scheduled_job():
    print("----- sendTasks started -----")
    sendTasks(getTaskList(init()))
    print("----- sendTasks done -----")


sched.start()
print("ITC-LMS: Bot initialized")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("function_name", type=str, help="set fuction name in this file")
    parser.add_argument(
        "-i", "--func_args", nargs="*", help="args in function", default=[]
    )
    args = parser.parse_args()

    # このファイル内の関数を取得
    func_dict = {k: v for k, v in locals().items() if callable(v)}
    # 引数のうち，数値として解釈できる要素はfloatにcastする
    func_args = [float(x) if x.isnumeric() else x for x in args.func_args]
    # 関数実行
    ret = func_dict[args.function_name](*func_args)
