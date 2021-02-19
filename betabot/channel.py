import json
import time

from betabot.bots.bot import Bot


class MetaString(str):
    _meta = dict()

class Channel(object):

    def __init__(self, bot: Bot, info):
        self.bot = bot
        self.info = info

    async def send(self, text, extra=None):
        # TODO: Help make this slack-specfic...
        return await self.bot.send(text, self.info.get('id'), extra)

    async def button_prompt(self, text, buttons) -> MetaString:
        button_actions = []
        for b in buttons:
            if type(b) == dict:
                button_actions.append(b)
            else:
                # assuming it's a string
                button_actions.append({
                    "type": "button",
                    "text": b,
                    "name": b,
                    "value": b
                })

        attachment = {
            "color": "#1E9E5E",
            "text": text,
            "actions": button_actions,
            "callback_id": str(id(self)),
            "fallback": text,
            "attachment_type": "default"
        }

        b = await self.bot.api('chat.postMessage', {
            'attachments': json.dumps([attachment]),
            'channel': self.info.get('id')})

        event = await self.bot.wait_for_event(type='message-action',
                                              callback_id=str(id(self)))
        action_value = MetaString(event['payload']['actions'][0]['value'])
        action_value._meta = {
            'event': event['payload']
        }

        attachment.pop('actions')  # Do not allow multiple button clicks.
        attachment['footer'] = '@{} selected "{}"'.format(event['payload']['user']['name'],
                                                          action_value)
        attachment['ts'] = time.time()

        await self.bot.api('chat.update', {
            'ts': b['ts'],
            'attachments': json.dumps([attachment]),
            'channel': self.info.get('id')})

        return action_value
