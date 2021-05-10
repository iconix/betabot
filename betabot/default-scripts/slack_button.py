# import json
# import logging

# from tornado import web

# import betabot.bots.bot

# BOT = betabot.bots.bot.get_instance()
# LOG = logging.getLogger(__name__)


# @bot.on(ok=False, error={"code": -1,
#                          "msg": "slow down, too many messages..."})
# async def slack_throttle(event):
#     LOG.warning('Detected a slow-down warning!')
#     BOT._too_fast_warning = True


# class SlackButtonAction(web.RequestHandler):

#     def get(self):
#         self.write('get')

#     def post(self):
#         # https://api.slack.com/docs/message-buttons#responding_to_message_actions
#         payload = self.get_body_argument('payload')
#         payload = json.loads(payload)

#         log.info('Received a button action. Adding to web events.')
#         bot._web_events.append({
#             # For Chat class
#             'text': '',
#             'user': payload['user']['id'],
#             'channel': payload['channel']['id'],

#             # For event listeners
#             'type': 'message-action',
#             'callback_id': payload['callback_id'],

#             # Original data
#             'payload': payload
#         })

#         # Slightly hacky: ping slack so that it responds with pong.
#         # This will cause the get_next_message to notice the web event above.
#         # Correct solution requires a lot more code.
#         bot.connection.write_message(json.dumps({"id": 0, "type": "ping"}))


# @bot.on_start
# async def add_handlers():
#     """Adds Slack specific handlers to the Bot's web_app."""
#     log.info('adding slack handlers')
#     try:
#         bot.add_web_handler(r'/slack-button-action', SlackButtonAction)
#     except betabot.bots.bot.WebApplicationNotAvailable:
#         log.error('unable to add slack callback.')
