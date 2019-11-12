# -*- coding: utf-8 -*-
"""
Anbindung an Telegram zum Versenden des Türstatus nach Änderung inkl. eines Steady-Shot
der Überwachungskamera.
"""
# --------------------------------------------------------------------------------------------------
import threading
from io import BytesIO
# --------------------------------------------------------------------------------------------------
import requests
import config
from tempcheck import settings
# --------------------------------------------------------------------------------------------------
STEADY_URL = 'http://localhost:%s/steady.jpg' % (config.CAM_PORT,)

TELEGRAM_URL = settings.TELEGRAM_URLTPL % (settings.TELEGRAM_BOTID, 'sendPhoto')

MESSAGE_TPL = {
    config.DOOR_OPEN:   'Tür wurde um {{dtnow:{0}}} geöffnet und wird {{close_time:{0}}} '
                        'wieder geschlossen.'.format(settings.MSG_TIMEFORMAT),
    config.DOOR_CLOSED: 'Tür wurde um {{dtnow:{0}}} geschlossen und wird {{open_time:{0}}} '
                        'wieder geöffnet.'.format(settings.MSG_TIMEFORMAT),
}

MESSAGE_DELAY = {
    config.DOOR_OPEN: config.NOTIFY_DOOR_OPEN_DELAY,
    config.DOOR_CLOSED: config.NOTIFY_DOOR_CLOSED_DELAY,
}
# --------------------------------------------------------------------------------------------------
def SendSteadyShot(logger, message):
    """
    Schickt ein aktuelles Bild von der Kamera mit der Nachricht ``message`` an den Telegram-Bot.
    Das Bild wird dabei vom Kameraserver per HTTP-Request geholt.
    """
    logger.debug("Requesting steady shot from %r", STEADY_URL)

    try:
        response = requests.get(STEADY_URL)
    except Exception as exc:
        logger.error('Failed to request steady shot from %r: %s', STEADY_URL, exc)
        return

    if response.status_code != requests.codes.ok:
        logger.warning(
            'Request of steady shot from %r failed with status %s.',
            STEADY_URL, response.status_code
        )
        return

    imgio = BytesIO(response.content)

    params = {
        'chat_id': settings.TELEGRAM_CHATID,
        'caption': message,
        'photo': 'attach://test-jpg'
    }

    try:
        response = requests.post(TELEGRAM_URL, params=params, files = {'test-jpg': imgio})
    except Exception as exc:
        logger.error('Failed to send steady shot to %r: %s', TELEGRAM_URL, exc)
        return

    if response.status_code != requests.codes.ok:
        logger.warning(
            'Sending notification via %r failed with status %s.',
            TELEGRAM_URL, response.status_code
        )
        return

    try:
        rjson = response.json()
        if not rjson['ok']:
            logger.warning(
                'Sending notification failed: %s', rjson
            )
    except Exception as exc:
        logger.exception('Received unexpected result from Bot.')

# --------------------------------------------------------------------------------------------------
def NotifyDoorAction(logger, action, dtnow, open_time, close_time):
    """
    Schickt eine Nachricht über :func:`SendSteadyShot` über die Änderung des Türzustands.
    Das Verschicken erfolgt asynchron in einem separatem Thread.

    :param action: Status der Tür (:obj:`config.DOOR_OPEN` oder :obj:`config.DOOR_CLOSED`).

    :param dtnow: Aktueller Zeitpunkt.

    :param open_time: Nächster geplanter Zeitpunkt zum Öffnen der Tür.

    :param open_time: Nächster geplanter Zeitpunkt zum Schließen der Tür.
    """
    message = MESSAGE_TPL.get(action, None)
    if message:

        message = message.format(
            dtnow = dtnow,
            open_time = open_time,
            close_time = close_time
        )

        delay = MESSAGE_DELAY.get(action, 5.0)

        logger.info("Scheduling notification in %.0f seconds.", delay)

        threading.Timer(
            delay,
            SendSteadyShot,
            args = (logger, message,)
        ).start()
# --------------------------------------------------------------------------------------------------
