import json
import logging
import time
import os
from enum import Enum
from datetime import datetime
import requests


webhook_url = os.getenv("SLACK_WEBHOOK_URL")

logger = logging.getLogger()
log_level = os.getenv("LOG_LEVEL") or "INFO"
numeric_log_level = getattr(logging, log_level.upper(), 10)
logger.setLevel(numeric_log_level)


class NotificationType(Enum):
    ALARM = 1
    NOTIFICATION = 2
    UNKNOWN = 3


def notification_type(subject):
    if "ALARM" in subject or "OK" in subject:
        return NotificationType.ALARM
    elif "Notification" in subject:
        return NotificationType.NOTIFICATION
    return NotificationType.UNKNOWN


def post_to_slack(attachments):
    """
    Post to Slack with JSON
    """
    param = {
        "username": "AWS Elastic Beanstalk Event notifier",
        "icon_emoji": ":aws_eb:",
        "attachments": attachments,
    }
    res = requests.post(webhook_url, json=param)
    if res.status_code != 200:
        logger.error("post_to_slack is failure. STATUS: {}, param: {}".format(res.status_code, param))
        return
    logger.info("post_to_slack is successful")


def attachments_for_notification(message):
    message = message.replace("\n\n", "\n").split("\n")
    message = dict(tuple(m.split(": ")) for m in message)
    text = message["Message"]
    status = text[text.find(" to")+4:text.find(".")]
    color = "good"
    if status == "Ok":
        status_emoji = ":ok_hand:"
    elif status == "Info":
        status_emoji = ""
    elif status == "Warning":
        color = "warning"
        status_emoji = ":warning:"
    elif status == "Degraded":
        color = "danger"
        status_emoji = ":exclamation:"
    elif status == "Severe":
        color = "danger"
        status_emoji = ":bangbang:"
    else:
        if text == "New application version was deployed to running EC2 instances.":
            status_emoji = ":arrow_heading_up:"
            status = "Deployed"
        else:
            status_emoji = ":question:"
            status = "Unknown"

    params = {
        "color": color,
        "pretext": "{} {}".format(status_emoji, text),
        "title": message["Environment URL"],
        "title_link": message["Environment URL"],
        "fields": [
            {
                "title": "Application",
                "value": message["Application"],
                "short": True
            },
            {
                "title": "Environment",
                "value": message["Environment"],
                "short": True
            },
            {
                "title": "Status",
                "value": status,
                "short": True
            }
        ],
    }
    return params


def attachments_for_alarm(message):
    message = json.loads(message)
    new_state = message["NewStateValue"]
    old_state = message["OldStateValue"]
    reason = message["NewStateReason"]
    color = "green"
    if new_state == "ALARM":
        color = "danger"
    elif new_state == "INSUFFICIENT":
        color = "warning"
    params = {
        "color": color,
        "pretext": "{old_state} :arrow_right: {new_state}".format(old_state=old_state, new_state=new_state),
        "text": reason
    }
    return params


def create_attachments(message, timestamp, notification_type):
    params = {}
    attachments = []
    if notification_type == NotificationType.NOTIFICATION:
        params = attachments_for_notification(message)
    elif notification_type == NotificationType.ALARM:
        params = attachments_for_alarm(message)
    else:
        params = {
            "color": "danger",
            "pretext": ":anger: Unexpected error. Please check Cloudwatch ALARM :anger:",
            "text": message,
        }
    params.update({
        "footer": "eb-events-to-slack",
        "ts": convert_unixtime(timestamp),
    })
    attachments.append(params)
    return attachments


def convert_unixtime(t):
    return int(time.mktime(datetime.strptime(t, "%Y-%m-%dT%H:%M:%S.%fZ").timetuple()))


def handle(event, context):
    logger.info("{} - {}".format(event, context))
    subject = event["Records"][0]["Sns"]["Subject"]
    message = event["Records"][0]["Sns"]["Message"]
    timestamp = event["Records"][0]["Sns"]["Timestamp"]
    attachments = create_attachments(message, timestamp, notification_type(subject))
    post_to_slack(attachments)
