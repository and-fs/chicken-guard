#!python3
# -*- coding: utf8 -*-
# ------------------------------------------------------------------------
import sys
import time
from datetime import datetime
from threading import Condition
# ------------------------------------------------------------------------
import lib_tft24t
import spidev
from PIL import ImageFont, Image
# ------------------------------------------------------------------------
import shared
from gpio import GPIO
from shared import LoggableClass
from config import * # pylint: disable=W0614
from tools import AsyncFunc, CallError, InstallStateChangeHandler
from datetime import datetime
# ------------------------------------------------------------------------
class ScreenController(LoggableClass):
    DC = 24
    RST = 25
    LED = 22
    TOUCH_IRQ = 26     # GPIO26
    SLEEP_TIMEOUT = TFT_SLEEP_TIMEOUT # Anzahl Sekunden nach dem letzten Touch bis der TFT deaktiviert wird
    FONT = ImageFont.truetype('/usr/share/fonts/truetype/lato/Lato-Medium.ttf', 16)
    FONT_BIG = ImageFont.truetype('/usr/share/fonts/truetype/lato/Lato-Medium.ttf', 22)
    BULB = Image.open(shared.resource_path.joinpath("bulb_white.png")).convert("RGBA")

    def __init__(self, logger):
        LoggableClass.__init__(self, logger = logger)
        self.door_state = "n/a"
        self.setState({})
        self.shutdown = False
        self._needs_update = True
        self.last_input = time.time()
        self.condition = Condition()
        self.tft_state = True
        self.light_state_indoor = False
        self.light_state_outdoor = False
        self.slots = { (250,  40, 310,  85): self.doorUp,
                       (250, 105, 310, 165): self.doorStop,
                       (250, 185, 310, 230): self.doorDown,
                       (  0, 200, 115, 240): self.switchOutdoorLight,
                       (116, 200, 230, 240): self.switchIndoorLight,
                       (  0,  50, 230, 100): self.switchDoorAutomatic,
                     }


        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        self.tft = lib_tft24t.TFT24T(spidev.SpiDev(), GPIO, landscape = True)
        self.tft.initLCD(self.DC, self.RST, self.LED, switch_on = self.tft_state)
        self.tft.initTOUCH(self.TOUCH_IRQ)
        # TOUCH_IRQ = Pen!
        GPIO.add_event_detect(self.TOUCH_IRQ, GPIO.BOTH, callback = self.onTouchEvent, bouncetime = 250)

        InstallStateChangeHandler(self, self.onStateChanged, self.shouldShutdown)

    def __call__(self):
        self.info("Started.")
        self.tft.clear()
        self.drawScreen()
        try:
            self.doWork()
        finally:
            self.doCleanup()
        self.info("Finished.")

    def GetNextActionText(self, state):
        if state.get("automatic", "True"):
            now = datetime.now()
            for dt, action in state.get("next_actions", []):
                if now < dt:
                    return "{0} um {1:%H:%M}".format(
                        "Öffnen" if action == DOOR_OPEN else "Schließen",
                        dt
                    )
            return "FEHLER"
        return "Manuell"

    def setState(self, state):
        # moving_up, closed, open, moving_down
        self.door_state = state.get("door", "n/a")
        self.light_state_indoor = state.get("indoor_light", False)
        self.light_state_outdoor = state.get("outdoor_light", False)
        
        try:
            tstr = "%2.f°C" % (state["temperature"],)
        except Exception:
            self.exception("Failed to handle temperatur from state: %r", state)
            tstr = "FEHLER"

        try:
            ls = state["light_sensor"]
        except KeyError:
            self.error("Missing 'light_sensor' in state: %r", state)
            lstr = "FEHLER"
        else:
            if ls > 200:
                lstr = "dunkel"
            elif ls > 120:
                lstr = "bewölkt"
            else:
                lstr = "sonnig"
        ns = {
            "door": self.door_state,
            "indoor_light": "an" if self.light_state_indoor else "aus",
            "outdoor_light": "an" if self.light_state_outdoor  else "aus",
            "temperature": tstr,
            "light_sensor": lstr,
            "next_action": self.GetNextActionText(state),
            "automatic": state.get("automatic", True),
        }

        self.state = ns

    def onStateChanged(self, state):
        print ("New state: ", state)
        self.setState(state)
        print ("Door state: ", self.door_state)
        self.needsUpdate()

    def needsUpdate(self):
        with self.condition:
            self._needs_update = True
            self.condition.notify_all()

    def switchTFT(self, switch_on = True):
        if self.tft_state == switch_on:
            return
        self.tft_state = switch_on
        if switch_on:
            self.tft.switchOn()
            self.debug("Switched TFT On.")
        else:
            self.tft.switchOff()
            self.debug("Switched TFT Off.")

    def shouldShutdown(self):
        return self.shutdown

    def doShutdown(self):
        """
        Setzt das shutdown-Flag und beendet somit
        die Ausführung der Loop in doWork.
        """
        if self.shutdown:
            return
        self.shutdown = True
        with self.condition:
            self.condition.notify_all()

    def doWork(self):
        """
        Main loop.
        """
        wait_time = min(60.0, self.SLEEP_TIMEOUT)
        last_screen_update = 0
        while not self.shutdown:
            update = False
            with self.condition:
                self.condition.wait(wait_time)
                if self.shutdown:
                    break
                update = self._needs_update
                self._needs_update = False
                if self.last_input + self.SLEEP_TIMEOUT < time.time():
                    self.switchTFT(switch_on = False)
            if not update:
                # wenn nicht ohnehin eine Aktualisierung anliegt,
                # führen wir spätestens nach 60s eine durch
                update = last_screen_update + 60.0 <= time.time()
            if update and self.tft_state:
                self.drawScreen()
                last_screen_update = time.time()

    def onTouchEvent(self, channel):
        print("Touch event!")
        self.last_input = time.time()
        if self.tft.penDown():
            if not self.tft_state:
                self.debug("Woke up display after inactivity.")
                self.switchTFT(switch_on = True)
                return
            position = self.tft.penPosition()
            self.debug("Touch at %r", position)
            print ("Touch at %r" % (position,))
            x, y = position
            for p, handler in self.slots.items():
                pleft, ptop, pright, pbottom = p
                if x < pleft or x > pright:
                    continue
                if y < ptop or y > pbottom:
                    continue
                try:
                    handler()
                except Exception:
                    self.logger.exception("Error in touch handler.")
                break
        else:
            print ("Touch up.")

    def doCleanup(self):
        self.debug("Cleaning up.")
        self.tft.switchOff()
        GPIO.cleanup()

    def OnDoorOpened(self, result = None):
        self.debug("Received door open callback: door is %s.", "open now" if result else "still closed")
        self.door_state = DOOR_OPEN
        self.needsUpdate()

    def doorUp(self):
        self.info("Door up button pressed.")
        self.door_state = DOOR_MOVING
        AsyncFunc("OpenDoor", callback = self.OnDoorOpened)()

    def OnDoorClosed(self, result = None):
        self.debug("Received door close callback: door is %s.", "closed now" if result else "still open")
        self.door_state = DOOR_CLOSED
        self.needsUpdate()

    def doorDown(self):
        self.info("Door down button pressed.")
        self.door_state = DOOR_MOVING
        AsyncFunc("CloseDoor", callback = self.OnDoorClosed)()

    def OnDoorStopped(self, result = None):
        self.debug("Received door stop callback: %r", result)
        self.door_state = DOOR_UNKNOWN
        self.needsUpdate()

    def doorStop(self):
        self.info("Door stop button pressed.")
        AsyncFunc("StopDoor", callback = self.OnDoorStopped)()

    def OnIndoorLightSwitched(self, result = None):
        self.debug("Received indoor light switch callback: %r", result)
        self.light_state_indoor = not self.light_state_indoor
        self.needsUpdate()

    def switchIndoorLight(self):
        self.info("Switching indoor light %s", "off" if self.light_state_indoor else "on")
        AsyncFunc("SwitchIndoorLight", callback = self.OnIndoorLightSwitched)(not self.light_state_indoor)

    def OnOutdoorLightSwitched(self, result = None):
        self.debug("Received outdoor light switch callback: %r", result)
        self.light_state_outdoor = not self.light_state_outdoor
        self.needsUpdate()

    def switchOutdoorLight(self):
        self.info("Switching outdoor light %s", "off" if self.light_state_outdoor else "on")
        AsyncFunc("SwitchOutdoorLight", callback = self.OnOutdoorLightSwitched)(not self.light_state_outdoor)

    def OnDoorAutomaticSwitched(self, result):
        self.debug("Received door automatic switch callback: %r", result)
        self.state["automatic"] = result
        self.needsUpdate()

    def switchDoorAutomatic(self):
        self.info("Switching door automatic %s", "off" if self.state["automatic"] else "on")
        AsyncFunc("SwitchDoorAutomatic", callback = self.OnDoorAutomaticSwitched)(not self.state["automatic"])

    def drawScreen(self):
        draw = self.tft.draw()
        draw.rectangle([(0, 0), (320, 240)], fill = "black")
        # rechter Rand (Türsteuerung)
        draw.text((265,  5), "TÜR", font = self.FONT, fill = "white")
        draw.line((230, 0, 230, 240), fill = "gray", width = 3)

        if self.door_state != DOOR_MOVING:
            if self.door_state != DOOR_OPEN:
                # oberes Dreieck (Öffnen, nur wenn nicht offen.)
                draw.polygon([(250, 85), (280, 40), (310, 85)], outline = "white", fill = "gray")
            elif self.door_state != DOOR_CLOSED:
                # unteres Dreieck (Schließen, nur wenn nicht geschlossen.)
                draw.polygon([(250, 185), (280, 230), (310, 185)], outline = "white", fill = "gray")

        # Viereck in Mitte (immer)
        draw.rectangle([(250, 105), (310, 165)], outline = "white", fill = "gray")

        # Untermalung "Demnächst" (Automatic-Button)
        if self.state.get("automatic", True):
            draw.rectangle([(0, 50), (230, 100)], fill = "#008000")
        else:
            draw.rectangle([(0, 50), (230, 100)], fill = "#800000")

        # Trennlinien
        draw.line((0, 50, 230, 50), fill = "gray", width = 3)
        draw.line((0, 100, 230, 100), fill = "gray", width = 3)
        draw.line((0, 150, 230, 150), fill = "gray", width = 3)
        draw.line((115, 100, 115, 240), fill = "gray", width = 3)

        # Info - Texte
        dt = datetime.now().strftime("%H:%M")
        draw.text((   5,   3), "Zeit:", font = self.FONT, fill = "yellow")
        draw.text((  10,  20), dt, font = self.FONT_BIG, fill = "white", align = "right")

        draw.text((   5,   53), "Demnächst:", font = self.FONT, fill = "yellow")
        draw.text((  10,   70), self.state["next_action"], font = self.FONT_BIG, fill = "white", align = "right")

        draw.text((   5,  103), "Temperatur:", font = self.FONT, fill = "yellow")
        draw.text((  10,  120), self.state["temperature"], font = self.FONT_BIG, fill = "white", align = "right")
        
        draw.text((  120,  103), "Lichtsensor:", font = self.FONT, fill = "yellow")
        draw.text((  130,  120), self.state["light_sensor"], font = self.FONT_BIG, fill = "white", align = "right")

        draw.text((   5,  153), "Tür:", font = self.FONT, fill = "yellow")

        if self.door_state == DOOR_OPEN:
            txt = "offen"
        elif self.door_state == DOOR_CLOSED:
            txt = "zu"
        else:
            txt = "???"

        draw.text((  10,  170), txt, font = self.FONT_BIG, fill = "white", align = "right")

        draw.text((  120,  153), "Licht:", font = self.FONT, fill = "yellow")
        draw.text((  130,  170), "todo", font = self.FONT_BIG, fill = "white", align = "right")

        # unterer Rand (Licht)
        draw.line((0, 200, 230, 200), fill = "gray", width = 3)

        if self.light_state_indoor and self.light_state_outdoor:
            draw.rectangle([(0, 201), (229, 240)], fill = "#A0A000")
        elif self.light_state_outdoor:
            draw.rectangle([(0, 201), (113, 240)], fill = "#A0A000")
        elif self.light_state_indoor:
            draw.rectangle([(117, 201), (229, 240)], fill = "#A0A000")

        draw.bitmap(( 40, 204), self.BULB) # außen
        draw.bitmap(( 157, 204), self.BULB) # innen
        try:
            self.tft.display()
        except Exception:
            self.logger.exception("Error while displaying tft!")
            self.needsUpdate()

def main():
    logger = shared.getLogger("ScreenController")

    try:
        ctrl = ScreenController(logger)
    except Exception:
        logger.exception("Error while initializing screen controller.")
        return -1

    try:
        ctrl()
    except Exception:
        logger.exception("Error while running screen controller.")
        return -2

    return 0

if __name__ == '__main__':
    sys.exit(main())