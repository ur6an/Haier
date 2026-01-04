from flask_simplelogin import SimpleLogin,is_logged_in,login_required, get_username
from werkzeug.security import check_password_hash, generate_password_hash
from schedule import every, run_pending, get_jobs, clear, cancel_job
from flask import Flask, flash, render_template, request, session, jsonify, redirect, Markup, send_file, url_for
from flask_babel import Babel, gettext
from pymodbus.client.sync import ModbusSerialClient
from w1thermsensor import W1ThermSensor
from werkzeug.utils import secure_filename
import collections
import paho.mqtt.client as mqtt
from termcolor import colored
from waitress import serve
from datetime import datetime
from flask_socketio import SocketIO, emit
from itertools import islice
import socketio
import HPi.GPIO as GPIO
import configparser
import subprocess
import threading
import requests
import logging
import time
import traceback
import jinja2
import pickle
import PyHaier
import urllib.request
import socket
import serial
import signal
import base64
import json
import time
import sys
import io
import os

# --- globals that must exist before threads start ---
services = []
event = threading.Event()

# Thermostat / heat demand debounce
# If inside temperature is above the high threshold, heat demand will turn OFF
# only after being above it for this many seconds.
# Override at runtime: export HEATDEMAND_OFF_DELAY_S=0
HEATDEMAND_OFF_DELAY_S = int(os.getenv("HEATDEMAND_OFF_DELAY_S", "30"))

# State for the debounce logic (timestamp when we first went above high threshold)
heatdemand_hi_since = None

version="1.4beta10"
ip_address=subprocess.run(['hostname', '-I'], check=True, capture_output=True, text=True).stdout.strip()
welcome="\n┌────────────────────────────────────────┐\n│              "+colored("!!!Warning!!!", "red", attrs=['bold','blink'])+colored("             │\n│      This script is experimental       │\n│                                        │\n│ Products are provided strictly \"as-is\" │\n│ without any other warranty or guaranty │\n│              of any kind.              │\n└────────────────────────────────────────┘\n","yellow", attrs=['bold'])
config = configparser.ConfigParser()
config.read('config.ini.repo')
config.read('/opt/config.ini')
log_level_info = {'DEBUG': logging.DEBUG, 
                    'INFO': logging.INFO,
                    'WARNING': logging.WARNING,
                    'ERROR': logging.ERROR,
                    }

SERVER_URL = "https://app.haierpi.pl"
TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoyfQ.uNzcoMkLSOONHZAOeEWI1l2KEAnzeh0DuADajOrWfUw'
sio_remote = socketio.Client(reconnection=True, reconnection_delay=1, reconnection_delay_max=10)
#, logger=True, engineio_logger=True)

custom_headers = {
    "User-Agent": "HaierPi/1.4"
}
remote=False
@sio_remote.event
def connect():
    logging.info("Connected to remote server")
    sio_remote.emit("connect_device", {"token": hpikey})

@sio_remote.event
def disconnect():
    logging.warning("Disconnected from server!")

@sio_remote.event
def connect_error(data):
    logging.error(f"Connection failed: {data}")

def loadconfig():
    global grestarted
    grestarted = 1
    logging.info("Loading new config.ini")
    global loglevel
    loglevel = config['MAIN']['log_level']
    global timeout
    timeout = config['MAIN']['heizfreq']
    global firstrun
    firstrun = config['MAIN']['firstrun']
    global bindaddr
    bindaddr = config['MAIN']['bindaddress']
    global bindport
    bindport = config['MAIN']['bindport']
    global modbusdev
    modbusdev = config['MAIN']['modbusdev']
    global release
    release = config['MAIN']['release']
    global expert_mode
    expert_mode = config['MAIN']['expert_mode']
    global settemp
    settemp = config['SETTINGS']['settemp']
    global slope
    slope = config['SETTINGS']['hcslope']
    global pshift
    pshift = config['SETTINGS']['hcpshift']
    global hcamp
    hcamp = config['SETTINGS']['hcamp']
    global heatingcurve
    heatingcurve = config['SETTINGS']['heatingcurve']
    global insidetemp
    insidetemp = config['SETTINGS']['insidetemp']
    global outsidetemp
    outsidetemp = config['SETTINGS']['outsidetemp']
    global omlat
    omlat = config['SETTINGS']['omlat']
    global omlon
    omlon = config['SETTINGS']['omlon']
    global humidity
    humidity = config['SETTINGS']['humidity']
    global flimit
    flimit = config['SETTINGS']['flimit']
    global flimittemp
    flimittemp = config['SETTINGS']['flimittemp']
    global presetautochange
    presetautochange = config['SETTINGS']['presetautochange']
    global presetquiet
    presetquiet = config['SETTINGS']['presetquiet']
    global presetturbo
    presetturbo = config['SETTINGS']['presetturbo']
    global antionoff
    antionoff = config['SETTINGS']['antionoff']
    global antionoffdelta
    antionoffdelta = config['SETTINGS']['antionoffdeltatime']
    global chscheduler
    chscheduler = config['SETTINGS']['chscheduler']
    global dhwscheduler
    dhwscheduler = config['SETTINGS']['dhwscheduler']
    global dhwwl
    dhwwl = config['SETTINGS']['dhwwl']
    global kwhnowcorr 
    kwhnowcorr = config['SETTINGS']['kwhnowcorr']
    global lohysteresis
    lohysteresis = config['SETTINGS']['lohysteresis']
    global hihysteresis
    hihysteresis = config['SETTINGS']['hihysteresis']
    global hcman
    hcman = config['SETTINGS']['hcman'].split(',')
    global hpiatstart
    hpiatstart = config['HPIAPP']['hpiatstart']
    global hpikey
    hpikey = config['HPIAPP']['hpikey']
    global use_mqtt
    use_mqtt = config['MQTT']['mqtt']
    global mqtt_broker_addr
    mqtt_broker_addr=config['MQTT']['address']
    global mqtt_broker_port
    mqtt_broker_port=config['MQTT']['port']
    global mqtt_ssl
    mqtt_ssl=config['MQTT']['mqtt_ssl']
    global mqtt_topic
    mqtt_topic=config['MQTT']['main_topic']
    global mqtt_username
    mqtt_username=config['MQTT']['username']
    global mqtt_password
    mqtt_password=config['MQTT']['password']
    global modbuspin
    modbuspin=config['GPIO']['modbus']
    global freqlimitpin
    freqlimitpin=config['GPIO']['freqlimit']
    global heatdemandpin
    heatdemandpin=config['GPIO']['heatdemand']
    global cooldemandpin
    cooldemandpin=config['GPIO']['cooldemand']
    global haaddr
    haaddr = config['HOMEASSISTANT']['HAADDR']
    global haport
    haport = config['HOMEASSISTANT']['HAPORT']
    global hakey
    hakey = config['HOMEASSISTANT']['KEY']
    global insidesensor
    insidesensor = config['HOMEASSISTANT']['insidesensor']
    global outsidesensor
    outsidesensor = config['HOMEASSISTANT']['outsidesensor']
    global humiditysensor
    humiditysensor = config['HOMEASSISTANT']['humiditysensor']
    global ha_mqtt_discovery
    ha_mqtt_discovery=config['HOMEASSISTANT']['ha_mqtt_discovery']
    global ha_mqtt_discovery_prefix
    ha_mqtt_discovery_prefix = config['HOMEASSISTANT']['ha_mqtt_discovery_prefix']
    global antionoffdeltatime
    antionoffdeltatime = config['SETTINGS']['antionoffdeltatime']
    global deltatempturbo
    deltatempturbo = config['SETTINGS']['deltatempturbo']
    global deltatempquiet
    deltatempquiet = config['SETTINGS']['deltatempquiet']
    global deltatempflimit
    deltatempflimit = config['SETTINGS']['deltatempflimit']

loadconfig()


# Create the stop event early so worker threads can safely reference it
def hpiapp(function='status'):
    if function == 'status':
        if hpiatstart == '1':
            if not sio_remote.connected:
                try:
                    logging.info("Trying to reconnect...")
                    sio_remote.connect(SERVER_URL, headers=custom_headers, wait_timeout=10)
                except Exception as e:
                    logging.error(f"Reconnect failed: {e}")
            else:
                try:
                    sio_remote.emit("heartbeat", {"token": TOKEN})
                except Exception as e:
                    logging.warning(f"Emit failed: {e}")

        status=sio_remote.sid
        ischanged('hpiconn', status)
    if function == 'disconnect':
        sio_remote.disconnect()
        status=sio_remote.connected
    if function == 'connect':
        try:
            sio_remote.connect(SERVER_URL,  headers=custom_headers, wait_timeout=10)
            status=sio_remote.connected
        except socketio.exceptions.ConnectionError as e:
            socketlocal.emit('return', {'info': e.args[0], 'status': 'danger'})
            logging.error(f"SERVER NIEDOSTEPNY: {e}")
            status=False

    socketlocal.emit('settings', {'hpiconn': status})
    return status

if hpiatstart == '1':
    try:
        sio_remote.connect(SERVER_URL,  headers=custom_headers, wait_timeout=10)
#        hpiapp('connect')
        remote=True
    except socketio.exceptions.ConnectionError as e:
        remote=False
        logging.error(type(e))
        logging.error(f"SERVER NIEDOSTEPNY: {e}")

newframe=[]
writed=""
needrestart=0
dead=0
datechart=collections.deque(8640*[''], 8640)
tankchart=collections.deque(8640*[''], 8640)
twichart=collections.deque(8640*[''], 8640)
twochart=collections.deque(8640*[''], 8640)
tdchart=collections.deque(8640*[''], 8640)
tschart=collections.deque(8640*[''], 8640)
thichart=collections.deque(8640*[''], 8640)
thochart=collections.deque(8640*[''], 8640)
taochart=collections.deque(8640*[''], 8640)
pdsetchart=collections.deque(8640*[''], 8640)
pdactchart=collections.deque(8640*[''], 8640)
pssetchart=collections.deque(8640*[''], 8640)
psactchart=collections.deque(8640*[''], 8640)
eevlevelchart=collections.deque(8640*[''], 8640)
tsatpdsetchart=collections.deque(8640*[''], 8640)
tsatpdactchart=collections.deque(8640*[''], 8640)
tsatpssetchart=collections.deque(8640*[''], 8640)
tsatpsactchart=collections.deque(8640*[''], 8640)
intempchart=collections.deque(8640*[''], 8640)
outtempchart=collections.deque(8640*[''], 8640)
humidchart=collections.deque(8640*[''], 8640)
hcurvechart=collections.deque(8640*[''], 8640)
fsetchart=collections.deque(8640*[''], 8640)
factchart=collections.deque(8640*[''], 8640)
flimitonchart=collections.deque(8640*[''], 8640)
modechart_quiet = collections.deque(8640*[0], 8640)
modechart_eco = collections.deque(8640*[0], 8640)
modechart_turbo = collections.deque(8640*[0], 8640)
threewaychart = collections.deque(8640*[''], 8640)
try:
    with open('charts.pkl', 'rb') as f:
        datechart, tankchart, twichart, twochart, tdchart, tschart, thichart, thochart, taochart, pdsetchart, pdactchart, pssetchart, psactchart, eevlevelchart, tsatpdsetchart, tsatpdactchart, tsatpssetchart, tsatpsactchart, intempchart, outtempchart, humidchart, hcurvechart, fsetchart, factchart, flimitonchart, modechart_quiet , modechart_eco , modechart_turbo, threewaychart = pickle.load(f)
except:
    logging.error("Cannot load charts pickle")


modbus =  ModbusSerialClient(method = "rtu", port=modbusdev,stopbits=1, bytesize=8, parity='E', baudrate=9600)
ser = serial.Serial(port=modbusdev, baudrate = 9600, parity=serial.PARITY_EVEN,stopbits=serial.STOPBITS_ONE,bytesize=serial.EIGHTBITS,timeout=1)
app = Flask(__name__)
babel = Babel()
UPLOAD_FOLDER = '/opt/haier'
ALLOWED_EXTENSIONS = {'hpi'}
app.config['SECRET_KEY'] = '2bb80d537b1da3e38bd30361aa855686bde0eacd7162fef6a25fe97bf527a25b'
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
socketlocal = SocketIO(app, compression=True)

@app.before_request
def make_session_permanent():
    session.permanent = True
set_log_level = log_level_info.get(loglevel, logging.ERROR)
logging.getLogger().setLevel(set_log_level)
flask_log=logging.getLogger('werkzeug')
flask_log.setLevel(logging.WARNING)

GPIO.setup(modbuspin, GPIO.OUT) #modbus
GPIO.setup(freqlimitpin, GPIO.OUT) #freq limit
GPIO.setup(heatdemandpin, GPIO.OUT) # heat demand
GPIO.setup(cooldemandpin, GPIO.OUT) # cool demand

statusdict={
'intemp':{'mqtt':'/intemp/state','value':'N.A.'},
'outtemp':{'mqtt':'/outtemp/state','value':'N.A.'},
'settemp':{'mqtt':'/temperature/state','value':settemp},
'hcurve':{'mqtt':'/heatcurve','value':'N.A.'},
'dhw':{'mqtt':'/dhw/temperature/state','value':'N.A.'},
'tank':{'mqtt':'/dhw/curtemperature/state','value':'N.A.'},
'mode':{'mqtt':'/preset_mode/state','value':'N.A.'},
'humid':{'mqtt':'/humidity/state','value':'N.A.'},
'pch':{'mqtt':'/details/pch/state','value':'off'},
'pdhw':{'mqtt':'/details/pdhw/state','value':'off'},
'pcool':{'mqtt':'/details/pcool/state','value':'off'},
'defrost':{'mqtt':'/details/defrost/state','value':'off'},
'tdef':{'mqtt':'/details/tdef/state','value':'N.A.'},
'theme':{'mqtt':'0','value':'light'},
'tdts':{'mqtt':'/details/tdts/state','value':'N.A.'},
'archerror':{'mqtt':'/details/archerror/state','value':'N.A.'},
'compinfo':{'mqtt':'/details/compinfo/state','value':'N.A.'},
'fans':{'mqtt':'/details/fans/state','value':'N.A.'},
'tao':{'mqtt':'/details/tao/state','value':'N.A.'},
'twitwo':{'mqtt':'/details/twitwo/state','value':'N.A.'},
'thitho':{'mqtt':'/details/thitho/state','value':'N.A.'},
'pump':{'mqtt':'/details/pump/state','value':'N.A.'},
'pdps':{'mqtt':'/details/pdps/state','value':'N.A.'},
'eevlevel': {'mqtt':'/details/eevlevel/state', 'value':'N.A.'},
'tsatpd': {'mqtt':'/details/tsatpd/state', 'value':'N.A.'},
'tsatps': {'mqtt':'/details/tsatps/state', 'value':'N.A.'},
'superheat': {'mqtt':'/details/superheat/state', 'value':'N.A.'},
'subcooling': {'mqtt':'/details/subcooling/state', 'value':'N.A.'},
'threeway':{'mqtt':'/details/threeway/state','value':'N.A.'},
'chkwhpd':{'mqtt':'/details/chkwhpd/state','value':'0'},
'dhwkwhpd':{'mqtt':'/details/dhwkwhpd','value':'0'},
'flimiton':{'mqtt':'/details/flimiton/state','value':'0'},
'antionoff':{'mqtt': '/antionoff/state', 'value':'N.A'},
'flimit':{'mqtt': '/flimit/state', 'value':'N.A'},
'delta':{'mqtt':'/details/delta/state','value':'N.A.'},
'hpiconn':{'mqtt':'/hpi/state', 'value':'N.A.'},
'heatdemand':{'mqtt':'/details/heatdemand/state','value':'N.A.'},
'cooldemand':{'mqtt':'/details/cooldemand/state','value':'N.A.'},
'flrelay':{'mqtt':'/details/flrelay/state','value':'N.A'},
'antionoffdeltatime':{'mqtt':'/details/antionoffdeltatime/state','value':'N.A.'},
'deltatempflimit':{'mqtt':'/details/deltatempflimit/state','value':'N.A.'},
'deltatempquiet':{'mqtt':'/details/deltatempquiet/state','value':'N.A.'},
'deltatempturbo': {'mqtt':'/details/deltatempturbo/state', 'value':'N.A.'}
}
R101=[0,0,0,0,0,0]
R141=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
R201=[0]
R241=[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
twocheck=[0,0]
last_check_time = 0
last_mode_active_ts = 0

DEFROST_FACT_HZ_MIN = 30.0 # minimal defrost compressor frequency


def _as_float(x):
    try:
        return float(x)
    except Exception:
        return None

def _as_int(x):
    try:
        return int(float(x))
    except Exception:
        return None


def GetTdef(payload):
    """
    Function for displaying Tdef parameter
    payload - register from 241 to 261
    :return:
    """
    if len(payload) == 22:
        tdef=[]
        tdefmsb=f'{divmod(int(hex(payload[12]), 16), 256)[0]:08b}'[0:4]
        tdeflsb=f'{divmod(int(hex(payload[13]), 16), 256)[0]:08b}'
        tdef = int(str(tdefmsb)+str(tdeflsb), 2)
        if tdef > 2047 :
            tdef -= 4095
        return tdef/10
    else:
        return "Bad payload length"

# NOWE --- Defrost detection ---
# We detect defrost from conditions you observed:
# - fans RPM goes to 0
# - compressor frequency (fact) is running (>= 30 Hz)
# - 3-way valve reports ERR (PyHaier returns 'ERR' for unknown states)
def _defrost_candidate():
    fans = statusdict.get("fans", {}).get("value", None)
    compinfo = statusdict.get("compinfo", {}).get("value", None)
    threeway = str(statusdict.get("threeway", {}).get("value", "")).strip().upper()

    # fan rpm == 0 (both fans, if list)
    fans0 = False
    if isinstance(fans, (list, tuple)) and len(fans) > 0:
        vals = []
        for f in fans:
            v = _as_int(f)
            if v is not None:
                vals.append(v)
        if len(vals) > 0:
            fans0 = all(v == 0 for v in vals)
    else:
        v = _as_int(fans)
        if v is not None:
            fans0 = (v == 0)

    # compressor frequency (fact) >= threshold
    fact = None
    if isinstance(compinfo, (list, tuple)) and len(compinfo) > 0:
        fact = _as_float(compinfo[0])
    else:
        fact = _as_float(compinfo)
    comp_on = (fact is not None and fact >= DEFROST_FACT_HZ_MIN)

    # 3-way valve err (PyHaier Get3way: CH / DHW / ERR)
    threeway_err = (threeway == "ERR")

    return fans0 and comp_on and threeway_err

def update_defrost_state():
    """Update statusdict['defrost'] directly from current conditions (no counters)."""
    cand = _defrost_candidate()
    cur = str(statusdict.get("defrost", {}).get("value", "off")).strip().lower()

    if cand and cur != "on":
        ischanged("defrost", "on")
    elif (not cand) and cur != "off":
        ischanged("defrost", "off")



def get_locale():
     return request.accept_languages.best_match(['en', 'pl'])

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def handler(signum, frame):
    logging.info(str(signum)+" "+str(signal.Signals(signum).name))
    print(colored("\rCtrl-C - Closing... please wait, this can take a while.", 'red', attrs=["bold"]))
    logging.info("writing charts to file")
    
    with open('charts.pkl', 'wb') as f:
        pickle.dump([datechart, tankchart, twichart, twochart, tdchart, tschart, thichart, thochart, taochart, pdsetchart, pdactchart, pssetchart, psactchart, eevlevelchart, tsatpdsetchart, tsatpdactchart, tsatpssetchart, tsatpsactchart, intempchart, outtempchart, humidchart, hcurvechart, fsetchart, factchart, flimitonchart, modechart_quiet, modechart_eco, modechart_turbo, threewaychart], f)

    GPIO.cleanup(modbuspin)
    GPIO.cleanup(freqlimitpin)
    GPIO.cleanup(heatdemandpin)
    GPIO.cleanup(cooldemandpin)
    if use_mqtt == '1':
        topic=str(client._client_id.decode())
        client.publish(topic + "/connected","offline", qos=1, retain=True)
        client.disconnect()
    event.set()
    clear()
    sys.exit()

def b2s(value):
    return (value and 'success') or 'error'

def is_raspberrypi():
    try:
        with io.open('/sys/firmware/devicetree/base/model', 'r') as m:
            if 'raspberry pi' in m.read().lower(): return True
    except Exception: pass
    return False

def isfloat(num):
    try:
        float(num)
        return True
    except ValueError:
        return False

def check_my_users(user):
    my_users = json.load(open("users.json"))
    if not my_users.get(user["username"]):
        return False
    stored_password = my_users[user["username"]]["password"]
    if check_password_hash(stored_password, user["password"]):
        return True
    return False
simple_login = SimpleLogin(app, login_checker=check_my_users)

def gpiocontrol(control, value):
    if control == "modbus":
        if value == "1":
            GPIO.output(modbuspin, GPIO.HIGH)
        elif value == "0":
            GPIO.output(modbuspin, GPIO.LOW)
    if control == "heatdemand":
        if value == "1":
            GPIO.output(heatdemandpin, GPIO.HIGH)
        if value == "0":
            GPIO.output(heatdemandpin, GPIO.LOW)
    if control == "cooldemand":
        if value == "1":
            GPIO.output(cooldemandpin, GPIO.HIGH)
        if value == "0":
            GPIO.output(cooldemandpin, GPIO.LOW)
    if control == "freqlimit":
        if value == "1":
            GPIO.output(freqlimitpin, GPIO.HIGH)
        if value == "0":
            GPIO.output(freqlimitpin, GPIO.LOW)

def queue_pub(dtopic, value):
    """Queue/publish value to all MQTT clients.
    Must be safe to call before MQTT thread finishes init."""
    global services
    try:
        clients = services
    except NameError:
        clients = []
    for clnt in list(clients):
        try:
            topic = str(clnt._client_id.decode() + statusdict[dtopic]['mqtt'])
            clnt.publish(topic, str(value), qos=1, retain=True)
        except:
            logging.error("MQTT: cannot publish "+dtopic)



def WritePump(newframe): #rewrited
    logging.info(f"Write pump, new frame: {newframe}")
    def WriteRegisters(count):
        global writed
        if count == 6:
            register = 101
        elif count == 1:
            register = 201
        time.sleep(1)
        modbus.connect()
        for x in range(5):
            time.sleep(1)
            logging.info("MODBUS: write register "+str(register)+", attempt: "+str(x)+" of 5")
            try:
                result=modbus.write_registers(register, newframe[1], unit=17)
                logging.info(f"Modbus write result: {result}")
                time.sleep(0.1)
                result=modbus.read_holding_registers(register, count, unit=17)
                logging.info(f"Newframe[0]: {newframe[0]}")
                logging.info(f"result.registers: {result.registers}")
                if result.registers != newframe[0]:
                    logging.info("MODBUS: Registers saved correctly")
                    writed="1"
                    break
            except:
                logging.info("MODBUS: Writing error, make another try...")
        modbus.close()
        gpiocontrol("modbus","0")
        return True
    logging.info("Writing Modbus Frame: "+str(newframe[1]))
    while True:
        rs = ser.read(1).hex()
        if rs == "032c":
            for ind in range(22):
                ser.read(2).hex()
        gpiocontrol("modbus", "1")
        break;
    if isinstance(newframe[1], (list, tuple, str)) and len(newframe[1]) in [1, 6]:
        try:
            WriteRegisters(len(newframe[1]))
        except:
            gpiocontrol("modbus", "0")
    else:
        logging.info("MODBUS: New frame has wrong length, exit")
        gpiocontrol("modbus", "0")
        return False

def ReadPump():
    global R101
    global R141
    global R201
    global R241
    global newframe
    T101=[]
    T141=[]
    T201=[]
    T241=[]
    time.sleep(0.2)
    while (1):
        if (ser.isOpen() == False):
            logging.warning(colored("Closed serial connection.", 'red', attrs=["bold"]))
            break
        if event.is_set():
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            ser.close()
            break
        if newframe:
            WritePump(newframe)
            newframe=[]
        try:
            rs = ser.read(1).hex()
            if rs == "11":
                rs = ser.read(2).hex()
                if rs == "030c":
                    T101 = []
                    D101 = []
                    for ind in range(6):
                        rs = ser.read(2).hex()
                        if rs:
                            T101.append(int(rs, 16))
                            m, l = divmod(int(rs, 16), 256)
                            D101.append(m)
                            D101.append(l)
                    R101=T101
                    threading.Thread(target=GetParametersNEW, args=(R101,), daemon=True).start()
                    logging.debug(D101)
                if rs == "0320":
                    T141 = []
                    D141 = []
                    for ind in range(16):
                        rs = ser.read(2).hex()
                        if rs:
                            T141.append(int(rs, 16))
                            m, l = divmod(int(rs, 16), 256)
                            D141.append(m)
                            D141.append(l)
                    R141=T141
                    threading.Thread(target=GetParametersNEW, args=(R141,), daemon=True).start()
                    logging.debug(D141)
                if rs == "0302":
                    T201 = []
                    for ind in range(1):
                        rs = ser.read(2).hex()
                        if rs:
                            T201.append(int(rs, 16))
                    logging.debug(R201)
                    R201=T201
                    threading.Thread(target=GetParametersNEW, args=(R201,), daemon=True).start()
                if rs == "032c":
                    T241 = []
                    D241 = []
                    for ind in range(22):
                        rs = ser.read(2).hex()
                        if rs:
                            T241.append(int(rs, 16))
                            m, l = divmod(int(rs, 16), 256)
                            D241.append(m)
                            D241.append(l)
                    R241=T241
                    threading.Thread(target=GetParametersNEW, args=(R241,), daemon=True).start()
                    logging.debug(D241)
        except:
            logging.error("ERROR ReadPump:")
            logging.error(traceback.print_exc())
            break

def on_connect(client, userdata, flags, rc):
    topic=str(client._client_id.decode())
    logging.info(colored("MQTT - Connected - "+topic, "green", attrs=['bold']))
    client.subscribe(topic + '/#')
    client.publish(topic + "/connected","online", qos=1, retain=True)
    if ha_mqtt_discovery == "1":
        if client._host != "haierpi.pl":
            client.subscribe(ha_mqtt_discovery_prefix+"/status")
            client.subscribe("hass/status")
            configure_ha_mqtt_discovery()


def on_disconnect(client, userdata, rc):  # The callback for when
    logging.warning(colored("Disconnected from MQTT with code: {0}".format(str(rc)), 'red', attrs=['bold']))

def on_message(client, userdata, msg):  # The callback for when a PUBLISH 
    topic=str(client._client_id.decode())
    if msg.topic == topic + "/power/set":
        logging.info("New power state from mqtt:")
        client.publish(topic + "/power/state",msg.payload.decode('utf-8'), qos=1, retain=True)
    elif msg.topic == topic + "/preset_mode/set":
        logging.info("New preset mode")
        payload=str(msg.payload.decode('utf-8')).lower()
        presets=['quiet', 'eco', 'turbo']
        if payload in presets:
            new_presetchange(payload)

    elif msg.topic == topic + "/flimit/set":
        logging.info("Frequency limit")
        try:
            flimitchange(str(msg.payload.decode('utf-8')))
        except:
            logging.error("MQTT: cannot set flimit relay")
    elif msg.topic == topic + "/mode/set":
        logging.info("New mode")
        newmode=msg.payload.decode('utf-8')
        if newmode == "heat":
            try:
                statechange("pch", "on", "1")
                client.publish(topic + "/mode/state",newmode, qos=1, retain=True)
            except:
                logging.error("MQTT: cannot set mode")
        elif newmode == "cool":
            try:
                statechange("pcool", "on", "1")
                client.publish(topic + "/mode/state",newmode, qos=1, retain=True)
            except:
                logging.error("MQTT: cannot set mode")
        elif newmode == "off":
            try:
                statechange("off", "off", "1")
                client.publish(topic + "/mode/state",newmode, qos=1, retain=True)
            except:
                logging.error("MQTT: cannot set mode")
        else:
            logging.error("MQTT: mode unsupported")

    elif msg.topic == topic + "/temperature/set":
        try:
            mesg,response = new_tempchange("heat",format(float(msg.payload.decode())),"0")
            if response:
                client.publish(topic + "/temperature/state",str(float(msg.payload.decode())), qos=1, retain=True)
        except:
            logging.error("MQTT: New temp error: payload - "+str(float(msg.payload.decode())))
    elif msg.topic == topic + "/dhw/mode/set":
        logging.info("New mode")
        payload=msg.payload.decode('utf-8')
        if payload == "heat":
            newmode="on"
        else:
            newmode=payload
        try:
            statechange("pdhw", str(newmode), "1")
            client.publish(topic + "/dhw/mode/state", str(payload), qos=1, retain=True)
        except:
            logging.error("MQTT: cannot change DHW mode - payload:"+str(newmode))
    elif msg.topic == topic + "/dhw/temperature/set":
        logging.info("New temperature")
        newtemp=int(float(msg.payload.decode('utf-8')))
        try:
            msg,response = new_tempchange("dhw", str(newtemp), "1")
            if response:
                client.publish(topic + "/dhw/temperature/state", str(newtemp), qos=1, retain=True)
        except:
            logging.error("MQTT: cannot change DHW temperature - payload:"+str(newtemp))
    elif msg.topic == ha_mqtt_discovery_prefix + "/status" or msg.topic == "hass/status":
        if ha_mqtt_discovery == "1":
            logging.info(msg.topic + " | " + msg.payload.decode('utf-8'))
            if msg.payload.decode('utf-8').strip() == "online":
                logging.info("Home Assistant online")
                configure_ha_mqtt_discovery()
    
##### NOWE
def set_newframe(register, frame):
    global newframe
    global writed
    newframe = [register, frame]
    for i in range(50):
        if writed=="1":
            writed="0"
            return True
        time.sleep(0.2)
    return False

def saveconfig(block, name, value):
    statusdict[name]['value'] = value
    config[block][name] = str(value)
    try:
        with open('/opt/config.ini', 'w') as configfile:
            config.write(configfile)
        return True
    except:
        return False

def new_tempchange(which, value, curve):
    global R101
    if curve == "1":
        if which == "heat":
            logging.info("Central heating: "+str(value))
            chframe = PyHaier.SetCHTemp(R101, float(value))
            response=set_newframe(R101,chframe)
            return 'Central Heating', response
        elif which == "dhw":
            logging.info("Domestic Hot Water: "+value)
            dhwframe = PyHaier.SetDHWTemp(R101, int(value))
            response=set_newframe(R101,dhwframe)
            queue_pub('dhw', value)
            return 'Domestic Hot Water', response
    elif curve == "0":
        if which == "heat":
            response = saveconfig('SETTINGS', 'settemp', float(value))
            queue_pub("settemp", value)
            if ha_mqtt_discovery=="1":
                Settemp_number.set_value(float(value))
            return 'Central Heating', response

def new_presetchange(mode):
    global R201
    logging.info("PRESET MODE: changed to: "+str(mode))
    response=set_newframe(R201,PyHaier.SetMode(mode))
    queue_pub('mode', mode)
    return 'Preset Mode', response

def new_flimitchange(mode):
    try:
        gpiocontrol("freqlimit", mode)
    except:
        return False

def flimitchange(mode):
    try:
        gpiocontrol("freqlimit", mode)
        msg="Frequency limit relay: "+str(mode)
        state="success"
        logging.info("Frequency limit relay changed to: "+ str(mode))
        if use_mqtt == "1":
            client.publish(mqtt_topic + "/flimit/state", str(mode), qos=1, retain=False)
        return msg,state
    except:
        msg="Frequency limit not changed"
        state="error"
        logging.error("Cannot change frequency limit relay")
        if use_mqtt == "1":
            client.publish(mqtt_topic + "/flimit/state", "error", qos=1, retain=False)
        return msg, state


def statechange(mode,value,mqtt):
    logging.info(f"passed values: mode - {mode}, value - {value}")
    def calculate_newstate(pdhw, pch, pcool, mode, value):
        if mode == 'pch':
            is_heating_on = (value == 'on')
        elif mode == 'off':
            is_heating_on = False
        else:
            is_heating_on = (pch == 'on')

        if mode == 'pcool':
            is_cooling_on = (value == 'on')
        elif mode == 'off': 
            is_cooling_on = False
        else:
            is_cooling_on = (pcool == 'on')

        if mode == 'pdhw':
            is_dhw_on = (value == 'on')
        else:
            is_dhw_on = (pdhw == 'on')
        
        if mode == 'pdhw' and value == 'off':
            is_dhw_on = False

        if mode == 'pch' and value == 'on':
            is_cooling_on = False
    
        if mode == 'pcool' and value == 'on':
            is_heating_on = False

        final_state = ""
        if is_heating_on:
            final_state += "H"
        elif is_cooling_on:
            final_state += "C"
    
        if is_dhw_on:
            final_state += "T"

        if not final_state:
            return "off"
    
        return final_state

    global R101
    pcool=statusdict['pcool']['value']
    defrost=statusdict.get('defrost', {}).get('value','off')
    pch=statusdict['pch']['value']
    pdhw=statusdict['pdhw']['value']
    newstate=""
    newstate = calculate_newstate(pdhw, pch, pcool, mode, value)
    global newframe
    global writed
    logging.info(f"statechange: {newframe}")
    logging.info(f"statechange values: {mode}, {value}")
    logging.info(f"statechange: {writed}")
    logging.info(f"statechange R101: {R101}")
    logging.info(f"statechange: {newstate}")
    if len(R101) > 1:
        if int(R101[0])%2 == 0:
            newframe=[R101, PyHaier.SetState(R101, "on")]
            time.sleep(2)
        newframe=[R101, PyHaier.SetState(R101,newstate)]
        for i in range(50):
            logging.info(f"writed: {writed}")
            if writed=="1":
                msg=gettext("State changed!")
                state="success"
                writed="0"
                break
            elif writed=="2":
                msg=gettext("Modbus communication error.")
                state="error"
                writed="0"
            else:
                msg=gettext("Modbus connection timeout.")
                state="error"
                writed="0"
            time.sleep(0.2)
    if mqtt == "1":
        return "OK"
    else:
        return jsonify(msg=msg, state=state)

def curvecalc():
    global heatdemand_hi_since
    insidetemp = None
    outsidetemp = None
    settemp = None
    heatcurve = None

    if expert_mode == "1":
        mintemp=float(20)
        maxtemp=float(55)
    else:
        mintemp=float(25)
        maxtemp=float(55)
    # ---- Inside temperature (already filtered at the source) ----
    if isfloat(statusdict['intemp']['value']):
        insidetemp = float(statusdict['intemp']['value'])
    # ----
    if isfloat(statusdict['outtemp']['value']):
        outsidetemp=float(statusdict['outtemp']['value'])
    if isfloat(statusdict['settemp']['value']):
        settemp=float(statusdict['settemp']['value'])
    global heatingcurve
    if heatingcurve == 'directly':
        heatcurve=settemp
    elif heatingcurve == 'auto':
        t1=(outsidetemp/(320-(outsidetemp*4)))
        t2=pow(settemp,t1)
        sslope=float(slope)
        ps=float(pshift)
        amp=float(hcamp)
        heatcurve = round((((0.55*sslope*t2)*(((-outsidetemp+20)*2)+settemp+ps)+((settemp-insidetemp)*amp))+ps)*2)/2
    elif heatingcurve == 'static':
        sslope=float(slope)
        heatcurve = round((settemp+(sslope*20)*pow(((settemp-outsidetemp)/20), 0.7))*2)/2
    elif heatingcurve == 'manual':
        if outsidetemp is not None:
            if float(outsidetemp) < -15:
                heatcurve=float(hcman[0])
            elif -15 <= outsidetemp < -10:
                heatcurve=float(hcman[1])
            elif -10 <= outsidetemp < -8:
                heatcurve=float(hcman[2])
            elif -8 <= outsidetemp < -6:
                heatcurve=float(hcman[3])
            elif -6 <= outsidetemp < -4:
                heatcurve=float(hcman[4])
            elif -4 <= outsidetemp < -2:
                heatcurve=float(hcman[5])
            elif -2 <= outsidetemp < 0:
                heatcurve=float(hcman[6])
            elif 0 <= outsidetemp < 2:
                heatcurve=float(hcman[7])
            elif 2 <= outsidetemp < 4:
                heatcurve=float(hcman[8])
            elif 4 <= outsidetemp < 6:
                heatcurve=float(hcman[9])
            elif 6 <= outsidetemp < 8:
                heatcurve=float(hcman[10])
            elif 8 <= outsidetemp < 10:
                heatcurve=float(hcman[11])
            elif 10 <= outsidetemp < 15:
                heatcurve=float(hcman[12])
            elif outsidetemp >= 15:
                heatcurve=float(hcman[13])
        else:
            logging.warning("Cannot calculate 'manual' heatcurve, no outside temperature reading.")

    queue_pub('hcurve', heatcurve)
    # Thermostat mode
    if mintemp <= heatcurve <= maxtemp:
        if insidetemp is not None and isfloat(insidetemp):
            low_th  = settemp - float(lohysteresis)
            high_th = settemp + float(hihysteresis)

            # Turn ON immediately
            if insidetemp < low_th:
                heatdemand_hi_since = None
                try:
                    if GPIO.input(heatdemandpin) != 1:
                        logging.info("Turn on heat demand")
                        gpiocontrol("heatdemand", "1")
                    if str(statusdict['hcurve']['value']) != str(heatcurve):
                        new_tempchange("heat", heatcurve, "1")
                except:
                    logging.error("Set chtemp ERROR")

            # Turn OFF only if above high threshold long enough (debounce)
            elif insidetemp > high_th:
                now_ts = time.time()
                if heatdemand_hi_since is None:
                    heatdemand_hi_since = now_ts
                elif (now_ts - heatdemand_hi_since) >= HEATDEMAND_OFF_DELAY_S:
                    if GPIO.input(heatdemandpin) != 0:
                        logging.info("Turn off heat demand (confirmed)")
                        gpiocontrol("heatdemand", "0")

            else:
                heatdemand_hi_since = None
                logging.info("Thermostat Mode: Don't do anything, the temperature is within the limits of the hysteresis")
    else:
        heatdemand_hi_since = None
        if GPIO.input(heatdemandpin) != 0:
            logging.info("Turn off heat demand")
            gpiocontrol("heatdemand", "0")
    #statusdict['hcurve']['value']=heatcurve
    ischanged("hcurve", heatcurve)
    threeway=statusdict['threeway']['value']
    compinfo=statusdict['compinfo']['value']
    pdhw=statusdict['pdhw']['value']
    if len(compinfo) > 0:
        if dhwwl=="1" and compinfo[0] != 0 and threeway == "DHW":
            logging.info("Dont change flimit in DHW mode")
        else:
            if flimit == "auto" and antionoff != "1" and pdhw == 'off':
                if outsidetemp >= float(flimittemp):
                    logging.info("Turn on freq limit")
                    flimitchange("1")
                elif outsidetemp <= float(flimittemp)+0.5:
                    logging.info("Turn off freq limit")
                    flimitchange("0")
            if presetautochange == "auto" and antionoff != "1" and pdhw == 'off':
                mode=statusdict['mode']['value']
                if outsidetemp >= float(presetquiet) and mode != "quiet":
                    new_presetchange("quiet")
                elif outsidetemp <= float(presetturbo) and mode != "turbo":
                    new_presetchange("turbo")
                elif outsidetemp > float(presetturbo) and outsidetemp < float(presetquiet) and mode != "eco":
                    new_presetchange("eco")
    return heatcurve

def updatecheck():
    gitver=subprocess.run(['git', 'ls-remote', 'origin', '-h', 'refs/heads/'+release ], stdout=subprocess.PIPE).stdout.decode('utf-8')[0:40]
    localver=subprocess.run(['cat', '.git/refs/heads/'+release], stdout=subprocess.PIPE).stdout.decode('utf-8')[0:40]
    if localver != gitver:
        msg=gettext("Available")
    else:
        msg=gettext("Not Available")
    return jsonify(update=msg)

def restart():
    subprocess.Popen("systemctl restart haier.service", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return jsonify(restarted="OK")

def getparams():
    isr241=1
    isr141=1
    while (isr241):
        if (len(R241) == 22):
            tdts=PyHaier.GetTdTs(R241)
            archerror=PyHaier.GetArchError(R241)
            compinfo=PyHaier.GetCompInfo(R241)
            fans=PyHaier.GetFanRpm(R241)
            pdps=PyHaier.GetPdPs(R241)
            eevlevel=PyHaier.GetEEVLevel(R241)
            tsatpd=PyHaier.GetTSatPd(R241)
            tsatps=PyHaier.GetTSatPs(R241)
            tao=PyHaier.GetTao(R241)
            isr241=0
    while (isr141):
        if (len(R141) == 16):
            twitwo = PyHaier.GetTwiTwo(R141)
            thitho = PyHaier.GetThiTho(R141)
            pump=PyHaier.GetPump(R141)
            threeway=PyHaier.Get3way(R141)
            isr141=0
    chkwhpd=statusdict['chkwhpd']['value']
    dhwkwhpd=statusdict['dhwkwhpd']['value']

    
    def _to_float(v):
        try:
            return float(v)
        except Exception:
            return None

    # NOWE - Liczenie przegrzania i dochłodzenia
    Ts = _to_float(tdts[1]) if isinstance(tdts, (list, tuple)) and len(tdts) > 1 else None  
    Thi = _to_float(thitho[0]) if isinstance(thitho, (list, tuple)) and len(thitho) > 1 else None
    TsatPs_act = _to_float(tsatps[1]) if isinstance(tsatps, (list, tuple)) and len(tsatps) > 1 else None
    TsatPd_act = _to_float(tsatpd[1]) if isinstance(tsatpd, (list, tuple)) and len(tsatpd) > 1 else None

    superheat  = f"{abs(Ts - TsatPs_act):.1f}" if (Ts is not None and TsatPs_act is not None) else "N.A."
    subcooling = f"{abs(TsatPd_act - Thi):.1f}" if (Thi is not None and TsatPd_act is not None) else "N.A."

    return twitwo, thitho, tdts, archerror, compinfo, fans, pdps, eevlevel, tsatpd, tsatps, tao, pump, threeway, chkwhpd, dhwkwhpd, superheat, subcooling

def getdata():
    heatdemand = GPIO.input(heatdemandpin)
    cooldemand = GPIO.input(cooldemandpin)
    flimiton = GPIO.input(freqlimitpin)
    # flrelay is a mirror of the physical FLimit relay state (GPIO)
    flrelay = flimiton
    
    compinfo = statusdict['compinfo']['value']
    intemp=statusdict['intemp']['value']
    outtemp=statusdict['outtemp']['value']
    stemp=statusdict['settemp']['value']
    hcurve=statusdict['hcurve']['value']
    dhw=statusdict['dhw']['value']
    tank=statusdict['tank']['value']
    mode=statusdict['mode']['value']
    humid=statusdict['humid']['value']
    pch=statusdict['pch']['value']
    pdhw=statusdict['pdhw']['value']
    pcool=statusdict['pcool']['value']
    defrost=statusdict.get('defrost', {}).get('value', 'off')
    tdef=statusdict.get('tdef', {}).get('value', 'N.A.')
    presetch = presetautochange 
    ltemp=flimittemp
    
    heatingcurve=config['SETTINGS']['heatingcurve']
    flimit = config['SETTINGS']['flimit']
    antionoff=config['SETTINGS']['antionoff']
    
    delta=statusdict.get("delta", {}).get("value", "N.A.")
    if isinstance(compinfo, list) and len(compinfo) > 0 and compinfo[0] == 0:
        delta = "N.A."
    
    ischanged("deltatempturbo", deltatempturbo)
    ischanged("deltatempquiet", deltatempquiet)
    ischanged("deltatempflimit", deltatempflimit)
    ischanged("heatdemand", heatdemand)
    ischanged("cooldemand", cooldemand)
    ischanged("flrelay", flrelay)
    ischanged("pch", pch)
    ischanged("pcool", pcool)
    ischanged("defrost", defrost)
    ischanged("tdef", tdef)
    ischanged("pdhw", pdhw)
    ischanged("antionoff", antionoff)
    ischanged("antionoffdeltatime", antionoffdeltatime)
    ischanged("flimit", flimit)
    ischanged("flimiton", flimiton)
    ischanged("hcurve", hcurve)
    ischanged("humid", humid)
    ischanged("intemp", intemp)
    ischanged("mode", mode)
    ischanged("outtemp", outtemp)
    ischanged("settemp", stemp)  # bo settemp = stemp
    ischanged("tank", tank)


    
    return jsonify(intemp=intemp, outtemp=outtemp, setpoint=stemp, hcurve=hcurve, dhw=dhw, tank=tank, mode=mode, humid=humid, pch=pch, pdhw=pdhw, pcool=pcool, defrost=defrost, tdef=tdef, flimit=flimit, heatdemand=heatdemand,cooldemand=cooldemand, flimiton=flimiton, ltemp=ltemp, presetch=presetch, presetquiet=presetquiet, presetturbo=presetturbo, heatingcurve=heatingcurve, deltatempturbo=deltatempturbo, deltatempquiet = deltatempquiet, deltatempflimit=deltatempflimit, antionoffdeltatime=antionoffdeltatime, delta=delta, antionoff=antionoff, compinfo=compinfo, flrelay=flrelay)

def get_json_data():
    heatdemand = GPIO.input(heatdemandpin)
    cooldemand = GPIO.input(cooldemandpin)
    flimiton = GPIO.input(freqlimitpin)
    # flrelay is a mirror of the physical FLimit relay state (GPIO)
    flrelay = flimiton
    intemp=statusdict['intemp']['value']
    outtemp=statusdict['outtemp']['value']
    stemp=statusdict['settemp']['value']
    hcurve=statusdict['hcurve']['value']
    dhw=statusdict['dhw']['value']
    tank=statusdict['tank']['value']
    mode=statusdict['mode']['value']
    humid=statusdict['humid']['value']
    pch=statusdict['pch']['value']
    pdhw=statusdict['pdhw']['value']
    pcool=statusdict['pcool']['value']
    defrost=statusdict.get('defrost', {}).get('value', 'off')
    tdef=statusdict.get('tdef', {}).get('value', 'N.A.')
    
    presetch = presetautochange
    ltemp = flimittemp
    
    heatingcurve = config['SETTINGS']['heatingcurve']
    antionoff = config['SETTINGS']['antionoff']
    flimit = config['SETTINGS']['flimit']
    
    isr241=1
    isr141=1
    while (isr241):
        if (len(R241) == 22):
            tdts=PyHaier.GetTdTs(R241)
            archerror=PyHaier.GetArchError(R241)
            compinfo=PyHaier.GetCompInfo(R241)
            fans=PyHaier.GetFanRpm(R241)
            pdps=PyHaier.GetPdPs(R241)
            eevlevel=PyHaier.GetEEVLevel(R241)
            tsatpd=PyHaier.GetTSatPd(R241)
            tsatps=PyHaier.GetTSatPs(R241)
            tao=PyHaier.GetTao(R241)
            isr241=0
    while (isr141):
        if (len(R141) == 16):
            twitwo = PyHaier.GetTwiTwo(R141)
            thitho = PyHaier.GetThiTho(R141)
            pump=PyHaier.GetPump(R141)
            threeway=PyHaier.Get3way(R141)
            isr141=0
    chkwhpd=statusdict['chkwhpd']['value']
    dhwkwhpd=statusdict['dhwkwhpd']['value']
    
    ischanged("deltatempturbo", deltatempturbo)
    ischanged("deltatempquiet", deltatempquiet)
    ischanged("deltatempflimit", deltatempflimit)
    ischanged("heatdemand", heatdemand)
    ischanged("cooldemand", cooldemand)
    ischanged("flrelay", flrelay)
    ischanged("pch", pch)
    ischanged("pcool", pcool)
    ischanged("pdhw", pdhw)
    ischanged("antionoff", antionoff)
    ischanged("antionoffdeltatime", antionoffdeltatime)
    ischanged("flimit", flimit)
    ischanged("flimiton", flimiton)
    ischanged("hcurve", hcurve)
    ischanged("humid", humid)
    ischanged("intemp", intemp)
    ischanged("mode", mode)
    ischanged("outtemp", outtemp)
    ischanged("settemp", stemp)  # bo settemp = stemp
    ischanged("tank", tank)
    
    return jsonify(locals())

def ischanged(old, new):
    old_value = statusdict[old]['value']
    if old_value != new:
        logging.info("ischanged: status "+str(old)+" has changed. Set new value - "+str(new))
        semit = {str(old):new}
        socketlocal.emit('data_update', semit)
        if remote:
            try:
                sio_emit={'data_update': semit}
                sio_remote.emit('data_from_device', sio_emit)
            except:
                logging.error("Brak połączenia ze zdalnym serwerem")

            if old=='pch':
                try:
                    sio_remote.emit('notify_changes',{old: new})
                except:
                    logging.error("Brak połączenia ze zdalnym serwerem")

        statusdict[old]['value']=new
        queue_pub(old, new)

def GetDHT22():
    # Pause DHT22 sampling during defrost: keep the last good values.
    if str(statusdict.get("defrost", {}).get("value", "off")).strip().lower() == "on":
        return statusdict['intemp']['value'], statusdict['humid']['value']

    if is_raspberrypi():
        dhtexec='dht22r'
    else:
        dhtexec='dht22n'

    try:
        result = subprocess.check_output('./bin/' + dhtexec)
        parts = result.decode('utf-8').strip().split('#')
        humid_raw = parts[0]
        intemp_raw = parts[1]

        intemp = round(float(intemp_raw), 1)
        humid = round(float(humid_raw), 1)

        # Basic sanity checks (DHT22 glitches can return absurd values)
        if not (-30.0 <= intemp <= 60.0):
            raise ValueError("DHT22 temp out of range")
        if not (0.0 <= humid <= 100.0):
            raise ValueError("DHT22 humidity out of range")

    except Exception:
        intemp = statusdict['intemp']['value']
        humid = statusdict['humid']['value']

    ischanged("intemp", intemp)
    ischanged("humid", humid)

    return intemp, humid


def GetInsideTemp(param):
    if param == "builtin":
        intemp=statusdict['intemp']['value']
        return intemp
    elif param == "ha":
        # connect to Home Assistant API and get status of inside temperature entity
        url=config['HOMEASSISTANT']['HAADDR']+":"+config['HOMEASSISTANT']['HAPORT']+"/api/states/"+config['HOMEASSISTANT']['insidesensor']
        headers = requests.structures.CaseInsensitiveDict()
        headers["Accept"] = "application/json"
        headers["Authorization"] = "Bearer "+config['HOMEASSISTANT']['KEY']
        try:
            resp=requests.get(url, headers=headers)
            json_str = json.dumps(resp.json())
        except requests.exceptions.RequestException as e:
            logging.error(e)
        try:
            if 'state' in json_str:
                response = json.loads(json_str)['state']
                response = float(response)
                if isinstance(response, float):
                    logging.info("Insidetemp is float")
                else:
                    logging.error("Error: is not float")
                    return
                response = round(response, 1)
            else:
                logging.error("Entity state not found")
                response = statusdict['intemp']['value']
        except:
            response = statusdict['intemp']['value']
        ischanged("intemp", response)
        return response
    else:
        return statusdict['intemp']['value']

def GetOutsideTemp(param):
    if param == "builtin":
        try:
            sensor = W1ThermSensor()
            temperature = sensor.get_temperature()
            if -55 < temperature < 125:
                ischanged("outtemp", temperature)
                return temperature
            else:
                logging.error("DS18b20: temperature out of range -55 to 125°C")
                return statusdict['outtemp']['value']
        except:
            logging.error("Error: cannot read outside temperature")
            return statusdict['outtemp']['value']
    elif param == "ha":
        # connect to Home Assistant API and get status of outside temperature entity
        url=config['HOMEASSISTANT']['HAADDR']+":"+config['HOMEASSISTANT']['HAPORT']+"/api/states/"+config['HOMEASSISTANT']['outsidesensor']
        headers = requests.structures.CaseInsensitiveDict()
        headers["Accept"] = "application/json"
        headers["Authorization"] = "Bearer "+config['HOMEASSISTANT']['KEY']
        try:
            resp = requests.get(url, headers=headers)
            json_str = json.dumps(resp.json())
        except requests.exceptions.RequestException as e:
            logging.error(e)
        try:
            if 'state' in json_str:
                response = json.loads(json_str)['state']
                response = float(response)
                if isinstance(response, float):
                    logging.info("Outsidetemp is float")
                else:
                    logging.error("Error: is not float")
                    return
            else:
                logging.error("Entity state not found")
                response = statusdict['outtemp']['value']
        except:
            logging.error("Error: cannot read outside temperature from HA")
            response = statusdict['outtemp']['value']
        ischanged("outtemp", response)
        return response
    elif param == "tao":
        temperature = statusdict['tao']['value']
        ischanged("outtemp", temperature)
        return temperature
    else:
        return statusdict['outtemp']['value']

def GetHumidity(param):
    if param == "builtin":
        humid=statusdict['humid']['value']
        return humid
    elif param == "ha":
        # connect to Home Assistant API and get status of inside humidity entity
        url=config['HOMEASSISTANT']['HAADDR']+":"+config['HOMEASSISTANT']['HAPORT']+"/api/states/"+config['HOMEASSISTANT']['humiditysensor']
        headers = requests.structures.CaseInsensitiveDict()
        headers["Accept"] = "application/json"
        headers["Authorization"] = "Bearer "+config['HOMEASSISTANT']['KEY']
        try:
            resp = requests.get(url, headers=headers)
            json_str = json.dumps(resp.json())
        except requests.exceptions.RequestException as e:
            logging.error(e)
        try:
            if 'state' in json_str:
                response = json.loads(json_str)['state']
            else:
                logging.error("GetHumidity: Entity state not found")
                response = statusdict['humid']['value']
        except:
                logging.error("Error: cannot read humidity from HA")
                response = statusdict['humid']['value']
        ischanged("humid", response)
        return response
    else:
        return statusdict['humid']['value']

def settheme(theme):
    statusdict['theme']['value']=theme
    return theme
        
def flimitreset():
    """ 
    Wyłączanie ograniczenia częstotliwości, jeśli kompresor nie pracuje 
    i anty on-off jest aktywne.
    """

    # Pobranie wartości z statusdict
    compinfo = statusdict.get('compinfo', {}).get('value', "N.A")
    pump_info = statusdict.get('pump', {})

    # Pobranie pierwszego elementu z listy compinfo (jeśli istnieje)
    if isinstance(compinfo, list) and len(compinfo) > 0:
        comp_status = compinfo[0]  # Pobieramy pierwszy element
    else:
        comp_status = "N.A"  # Jeśli `compinfo` nie jest listą lub jest puste, zwracamy "N.A"

    # Jeśli kompresor pracuje (comp_status != 0), kończymy funkcję natychmiast
    if comp_status != 0:
        logging.info(f"Flimitreset: Function inactive.")
        return
        
    # Sprawdzenie czy klucze istnieją w statusdict
    if 'flimiton' in statusdict:
        flimiton = str(statusdict['flimiton'].get('value', "N.A"))
    else:
        logging.warning("Flimitreset: Brak klucza 'flimiton' w statusdict!")
        flimiton = "N.A"

    if 'antionoff' in statusdict:
        antionoff = str(statusdict['antionoff'].get('value', "N.A"))
    else:
        logging.warning("Flimitreset: Brak klucza 'antionoff' w statusdict!")
        antionoff = "N.A"

    if 'flimit' in statusdict:
        flimit = str(statusdict['flimit'].get('value', "N.A"))
    else:
        logging.warning("Flimitreset: Brak klucza 'flimit' w statusdict!")
        flimit = "N.A"
        
    if isinstance(pump_info, dict) and 'value' in pump_info:
        pump = pump_info['value']
    else:
        logging.warning("Flimitreset: Brak klucza 'pump' w statusdict!")
        pump = "N.A."
        
       

    # Sprawdzenie warunków i wyłączenie ograniczenia częstotliwości
    if flimiton == "1" and antionoff == "1" and flimit != "manual" and pump == "OFF":
        logging.info("Flimitreset: Forcing OFF frequency limit")
        flimitchange("0")
    else:
        logging.info("Flimitreset: No action needed.")

def deltacheck(temps):  # AntiON-OFF, Delta liczona z Zadanej CO i temp. powrotu (Twi)
    global last_check_time, antionoff, antionoffdeltatime, deltatempturbo, deltatempquiet, deltatempflimit

    try:  # Pobranie wartości:
        twitwo = statusdict.get('twitwo', {}).get('value', [None])  # Pobranie temperatury z listy Twi-Two
        compinfo = statusdict.get('compinfo', {}).get('value', [0])  # Status kompresora
        mode = statusdict.get('mode', {}).get('value', "")  # Tryb pracy pompy
        threeway = statusdict.get('threeway', {}).get('value', "")  # Status zaworu 3-drożnego
        flimiton = statusdict.get('flimiton', {}).get('value', "0")  # Status przekaźnika
        current_time = time.time()

        mode = str(mode).strip().lower()
        threeway = str(threeway).strip().upper()

        if threeway != "CH":
            last_check_time = current_time
            return

        if compinfo[0] == 0:
            last_check_time = current_time
            return

        hcurve = None
        if isfloat(statusdict.get('hcurve', {}).get('value', "N.A")):
            hcurve = float(statusdict['hcurve']['value'])
            
                     
        # Sprawdzenie warunków do uruchomienia funkcji:
        if antionoff == '1' and compinfo[0] != 0 and threeway == "CH" and hcurve is not None and twitwo[0] is not None:
            logging.info("AntiON-OFF: Function is active")
            

            # Sprawdzenie, czy minął wymagany czas:
            if current_time - last_check_time >= float(antionoffdeltatime) * 60:  # Czas w minutach podawany w Ustawieniach
                logging.info(f"AntiON-OFF: Taken values ​​to calculate the delta: Twi: {twitwo[0]}, Set temp: {hcurve}")  # Jakie wartości są pobierane do liczenia delty.
                delta = round(hcurve - twitwo[0], 1)  # Wynik
                logging.info(f"AntiON-OFF: Delta is: {delta} and current mode: {mode} and frequency limit: {flimiton}")  # Informacja o wyniku i trybie jednostki
                ischanged("delta", delta)
                ischanged("deltatempquiet", deltatempquiet)
                ischanged("deltatempturbo", deltatempturbo)
                ischanged("deltatempflimit", deltatempflimit)

                # Sprawdzanie czy wartości są liczbami:
                if isfloat(deltatempflimit) and isfloat(deltatempturbo) and isfloat(deltatempquiet):
                    deltatempflimit = float(deltatempflimit)
                    deltatempturbo = float(deltatempturbo)
                    deltatempquiet = float(deltatempquiet)

                    # Zmiana trybu pracy pompy
                    if delta > deltatempturbo:
                        if mode != "turbo":
                            logging.info(f"AntiON-OFF: Delta {delta} > {deltatempturbo}, changing mode to Turbo")
                            new_presetchange("turbo")

                        else:
                            logging.info(f"AntiON-OFF: No need to change mode (already Turbo).")

                    elif deltatempquiet <= delta <= deltatempturbo:
                        if mode != "eco":
                            logging.info(f"AntiON-OFF: Delta {delta} is in range ({deltatempquiet}, {deltatempturbo}), changing mode to Eco")
                            new_presetchange("eco")
                            
                        else:
                            logging.info(f"AntiON-OFF: Delta is {delta}, no need to change mode (already Eco).")

                    elif delta < deltatempquiet:
                        if mode != "quiet":
                            logging.info(f"AntiON-OFF: Delta {delta} is in range ({deltatempflimit}, {deltatempquiet}), changing mode to Quiet")
                            new_presetchange("quiet")
                            
                        else:
                            logging.info(f"AntiON-OFF: No need to change mode (already Quiet).")
                  

                    # Sterowanie ograniczeniem częstotliwości tylko w trybie quiet
                    if flimit != 'manual':
                        if delta < deltatempflimit:
                            if flimiton != "1":
                                logging.info(f"AntiON-OFF: Delta {delta} < {deltatempflimit}, turning ON frequency limit")
                                flimitchange("1")
                            else:
                                logging.info(f"AntiON-OFF: Frequency limit already ON, no action needed.")
                        elif delta > deltatempflimit:
                            if flimiton != "0":
                                logging.info(f"AntiON-OFF: Delta {delta} > {deltatempflimit}, turning OFF frequency limit")
                                flimitchange("0")
                            else:
                                logging.info(f"AntiON-OFF: Frequency limit already OFF, no action needed.")

                else:
                    logging.error("AntiON-OFF: One or more delta values are not valid numbers!")

                last_check_time = current_time

    except (KeyError, ValueError, TypeError) as e:
        logging.info(f"Error in deltacheck: {e}")


def schedule_write(which, data):
    if which == "ch":
        try:
            f = open("schedule_ch.json", "w")
            f.write(data)
            f.close()
            msg = gettext("Central Heating chedule saved")
            state = "success"
            return msg, state
        except:
            msg = gettext("ERROR: Central Heating not saved")
            state = "error"
            return msg, state
    if which == "dhw":
        try:
            f = open("schedule_dhw.json", "w")
            f.write(data)
            f.close()
            msg = gettext("Domestic Hot Water chedule saved")
            state = "success"
            return msg, state
        except:
            msg = gettext("ERROR: Domestic Hot Water not saved")
            state = "error"
            return msg, state

def scheduler():
    if chscheduler == "1":
        f=open('schedule_ch.json', 'r')
        data = json.load(f)
        now=datetime.now().strftime("%H:%M")
        weekday=datetime.weekday(datetime.now())
        pch=statusdict['pch']['value']
        schedulestart=[]
        for x in range(len(data[weekday]['periods'])):
            y=x-1
            start=data[weekday]['periods'][y]['start']
            end=data[weekday]['periods'][y]['end']
            if end >= now >= start:
                if pch == 'off':
                    schedulestart.append('on')
                    temp=data[weekday]['periods'][y]['title']
                else:
                    schedulestart.append('aon')
                    temp=data[weekday]['periods'][y]['title']
            else:
                if pch == 'on':
                    schedulestart.append('off')
                else:
                    schedulestart.append('aoff')
        if 'on' in schedulestart:
            logging.info("Scheduler: START CH")
            statechange("pch", "on", "1")
            if not temp == "":
                logging.info(f"Scheduler: Set new temp: {temp}")
                new_tempchange("heat",format(float(temp)),"0")
        elif 'aon' in schedulestart:
            logging.info("Scheduler: CH ALREADY ON")
            if not temp == "":
                stemp=statusdict['settemp']['value']
                if not stemp == temp:
                    logging.info(f"Scheduler: Set new temp: {temp}")
                    new_tempchange("heat",format(float(temp)),"0")
        elif 'aoff' in schedulestart:
            logging.info("Scheduler: CH ALREADY OFF")
        else:
            if pch != 'off':
                logging.info("Scheduler: STOP CH")
                statechange("off", "off", "1")
    if dhwscheduler == "1":
        f=open('schedule_dhw.json', 'r')
        data = json.load(f)
        now=datetime.now().strftime("%H:%M")
        weekday=datetime.weekday(datetime.now())
        pdhw=statusdict['pdhw']['value']
        schedulestart=[]
        for x in range(len(data[weekday]['periods'])):
            y=x-1
            start=data[weekday]['periods'][y]['start']
            end=data[weekday]['periods'][y]['end']
            if end >= now >= start:
                if pdhw == 'off':
                    schedulestart.append('on')
                else:
                    schedulestart.append('aon')
            else:
                if pdhw == 'on':
                    schedulestart.append('off')
                else:
                    schedulestart.append('aoff')
        if 'on' in schedulestart:
            logging.info("Scheduler: START DHW")
            statechange("pdhw", "on", "1")
        elif 'aon' in schedulestart:
            logging.info("Scheduler: DHW ALREADY ON")
        elif 'aoff' in schedulestart:
            logging.info("Scheduler: DHW ALREADY OFF")
        else:
            logging.info("Scheduler: STOP DHW")
            statechange("pdhw", "off", "1")


def GetParametersNEW(reg):
    regnum = len(reg)

    if regnum == 6:
        dhw = PyHaier.GetDHWTemp(reg)
        powerstate = PyHaier.GetState(reg)
        ischanged("dhw", dhw)

        heat_on = ('Heat' in powerstate)
        cool_on = ('Cool' in powerstate)
        tank_on = ('Tank' in powerstate)

        ischanged("pch", "on" if heat_on else "off")
        ischanged("pcool", "on" if cool_on else "off")
        ischanged("pdhw", "on" if tank_on else "off")

        # Publish consolidated HVAC/DHW modes for HA (and other MQTT clients)
        global last_mode_active_ts
        if use_mqtt == "1":
            now_ts = time.time()
            if heat_on:
                last_mode_active_ts = now_ts
                client.publish(mqtt_topic + "/mode/state", "heat", qos=1, retain=True)
            elif cool_on:
                last_mode_active_ts = now_ts
                client.publish(mqtt_topic + "/mode/state", "cool", qos=1, retain=True)
            else:
                # publish OFF only after a short debounce (prevents 1-frame glitches)
                if now_ts - last_mode_active_ts > 5:
                    client.publish(mqtt_topic + "/mode/state", "off", qos=1, retain=True)

            client.publish(mqtt_topic + "/dhw/mode/state", "heat" if tank_on else "off", qos=1, retain=True)

    elif regnum == 16:
        tank = PyHaier.GetDHWCurTemp(reg)
        twitwo = PyHaier.GetTwiTwo(reg)
        thitho = PyHaier.GetThiTho(reg)
        pump = PyHaier.GetPump(reg)
        threeway = PyHaier.Get3way(reg)
        ischanged("tank", tank)
        ischanged("twitwo", twitwo)
        ischanged("thitho", thitho)
        ischanged("pump", pump)
        ischanged("threeway", threeway)
        update_defrost_state()

    elif regnum == 1:
        mode = PyHaier.GetMode(reg)
        ischanged("mode", mode)

    elif regnum == 22:
        tdts = PyHaier.GetTdTs(reg)
        archerror = PyHaier.GetArchError(reg)
        compinfo = PyHaier.GetCompInfo(reg)
        fans = PyHaier.GetFanRpm(reg)
        pdps = PyHaier.GetPdPs(reg)
        eevlevel = PyHaier.GetEEVLevel(reg)
        tsatpd = PyHaier.GetTSatPd(reg)
        tsatps = PyHaier.GetTSatPs(reg)
        tao = PyHaier.GetTao(reg)
        tdef = GetTdef(reg)
        if isinstance(tdef, (int, float)):
            ischanged("tdef", tdef)

        def _to_float(v):
            try:
                return float(v)
            except Exception:
                return None
        # Superheating / Supercooling calculate        
        thitho = statusdict.get("thitho", {}).get("value", [None, None])
        Ts = _to_float(tdts[1]) if isinstance(tdts,(list,tuple)) and len(tdts)>1 else None
        Thi = _to_float(thitho[0]) if isinstance(thitho,(list,tuple)) and len(thitho)>1 else None
        TsatPs_act = _to_float(tsatps[1]) if isinstance(tsatps,(list,tuple)) and len(tsatps)>1 else None
        TsatPd_act = _to_float(tsatpd[1]) if isinstance(tsatpd,(list,tuple)) and len(tsatpd)>1 else None

        superheat  = f"{abs(Ts - TsatPs_act):.1f}" if (Ts is not None and TsatPs_act is not None) else "N.A."
        subcooling = f"{abs(TsatPd_act - Thi):.1f}" if (Thi is not None and TsatPd_act is not None) else "N.A."

        ischanged("superheat", superheat)
        ischanged("subcooling", subcooling)

        ischanged("tdts", tdts)
        ischanged("archerror", archerror)
        ischanged("compinfo", compinfo)
        ischanged("pdps", pdps)
        ischanged("eevlevel", eevlevel)
        ischanged("tsatpd", tsatpd)
        ischanged("tsatps", tsatps)
        ischanged("fans", fans)
        ischanged("tao", tao)
        update_defrost_state()


def GetParameters():
    global datechart
    global tankchart
    global twichart
    global twochart
    global thichart
    global thochart
    global taochart
    global pdsetchart
    global pdactchart
    global pssetchart
    global psactchart
    global intempchart
    global outtempchart
    global humidchart
    global hcurvechart
    global fsetchart
    global factchart
    global flimitonchart
    global modechart_quiet
    global modechart_eco
    global modechart_turbo
    global threeway_chart
    
    # Update defrost state before deciding about DHT22 sampling
    update_defrost_state()

    if str(statusdict.get("defrost", {}).get("value", "off")).strip().lower() != "on":
        if insidetemp == 'builtin' or humidity == 'builtin':
            threading.Thread(target=GetDHT22, daemon=True).start()
            threading.Thread(target=GetInsideTemp, args=(insidetemp,), daemon=True).start()
            threading.Thread(target=GetOutsideTemp, args=(outsidetemp,), daemon=True).start()
            threading.Thread(target=GetHumidity, args=(humidity,), daemon=True).start()
            threading.Thread(target=hpiapp, daemon=True).start()
            now=datetime.now().strftime("%d %b %H:%M:%S")
            datechart.append(str(now))
            tank=statusdict['tank']['value']
            twitwo=statusdict['twitwo']['value']
            thitho=statusdict['thitho']['value']
            pump=statusdict['pump']['value']
            threeway=statusdict['threeway']['value']
            mode=statusdict['mode']['value']
            dhwkwhpd=statusdict['dhwkwhpd']['value']
            chkwhpd=statusdict['chkwhpd']['value']
            tdts=statusdict['tdts']['value']
            archerror=statusdict['archerror']['value']
            compinfo=compinfo=statusdict['compinfo']['value']
            preset=statusdict['mode']['value']
            pdps=statusdict['pdps']['value']
            eevlevel=statusdict['eevlevel']['value']
            tsatpd=statusdict['tsatpd']['value']
            tsatps=statusdict['tsatps']['value']
            fans=statusdict['fans']['value']
            tao=statusdict['tao']['value']
            dhw=statusdict['dhw']['value']
            intemp=statusdict['intemp']['value']
            outtemp=statusdict['outtemp']['value']
            humid=statusdict['humid']['value']
            hcurve=statusdict['hcurve']['value']
            flimiton_gpio = str(GPIO.input(freqlimitpin))
            ischanged("flimiton", flimiton_gpio)
            flimiton=statusdict['flimiton']['value']
            threeway=statusdict['threeway']['value']
            if mode == "quiet":
                mode_q=1
                mode_e=0
                mode_t=0
            elif mode == "eco":
                mode_q=0
                mode_e=2
                mode_t=0
            elif mode == "turbo":
                mode_q=0
                mode_e=0
                mode_t=3
            else:
                mode_q=0
                mode_e=0
                mode_t=0
            tankchart.append(tank)
            twichart.append(twitwo[0])
            twochart.append(twitwo[1])
            thichart.append(thitho[0])
            thochart.append(thitho[1])
            modechart_quiet.append(mode_q)
            modechart_eco.append(mode_e)
            modechart_turbo.append(mode_t)
            tdchart.append(tdts[0])
            tschart.append(tdts[1])
            factchart.append(compinfo[0])
            fsetchart.append(compinfo[1])
            pdsetchart.append(pdps[0])
            pdactchart.append(pdps[1])
            pssetchart.append(pdps[2])
            psactchart.append(pdps[3])
            eevlevelchart.append(eevlevel)
            tsatpdsetchart.append(tsatpd[0])
            tsatpdactchart.append(tsatpd[1])
            tsatpssetchart.append(tsatps[0])
            tsatpsactchart.append(tsatps[1])
            taochart.append(tao)
            intempchart.append(intemp)
            outtempchart.append(outtemp)
            humidchart.append(humid)
            hcurvechart.append(hcurve)
            flimitonchart.append(flimiton)
            threewaychart.append(threeway)
            socketlocal.emit("chart_update", {'datechart': str(now), 'tankchart': tank, 'twichart': twitwo[0], 'twochart': twitwo[1], 'thichart': thitho[0], 'thochart': thitho[1], 'taochart': tao, 'tdchart': tdts[0], 'tschart': tdts[1], 'pdsetchart': pdps[0], 'pdactchart': pdps[1], 'pssetchart': pdps[2], 'psactchart': pdps[3], 'intempchart': statusdict['intemp']['value'], 'outtempchart': statusdict['outtemp']['value'], 'humidchart': statusdict['humid']['value'], 'hcurvechart': statusdict['hcurve']['value'], 'factchart': compinfo[0], 'fsetchart': compinfo[1], 'flimitonchart': statusdict['flimiton']['value']*2, 'modechart_quiet': mode_q, 'modechart_eco': mode_e, 'modechart_turbo': mode_t, 'threewaychart': threeway })
            deltacheck(twitwo)
            flimitreset()
            scheduler()
            if isinstance(compinfo, list) and len(compinfo) > 0:
                if dhwwl == "1" and compinfo[0] > 0 and threeway == "DHW" and (flimiton == "1" or preset != "turbo"):
                    logging.info("DHWWL Function ON")
                    flimitchange("0")
                    new_presetchange("turbo")
        """    if len(R141) == 16:
                tank = PyHaier.GetDHWCurTemp(R141)
                twitwo = PyHaier.GetTwiTwo(R141)
                thitho = PyHaier.GetThiTho(R141)
                pump=PyHaier.GetPump(R141)
                threeway=PyHaier.Get3way(R141)
                ischanged("tank", tank)
                tankchart.append(tank)
                ischanged("twitwo", twitwo)
                twichart.append(twitwo[0])
                twochart.append(twitwo[1])
                ischanged("thitho", thitho)
                thichart.append(thitho[0])
                thochart.append(thitho[1])
                ischanged("pump", pump)
                ischanged("threeway", threeway)
                update_defrost_state()
                deltacheck(twitwo)
                flimitreset()
            if len(R201) == 1:
                mode=PyHaier.GetMode(R201)
                ischanged("mode", mode)
                if mode == "quiet":
                    mode_q=1
                    mode_e=0
                    mode_t=0
                elif mode == "eco":
                    mode_q=0
                    mode_e=2
                    mode_t=0
                elif mode == "turbo":
                    mode_q=0
                    mode_e=0
                    mode_t=3
                else:
                    mode_q=0
                    mode_e=0
                    mode_t=0
                modechart_quiet.append(mode_q)
                modechart_eco.append(mode_e)
                modechart_turbo.append(mode_t)

            if len(R241) == 22:
                tdts=PyHaier.GetTdTs(R241)
                archerror=PyHaier.GetArchError(R241)
                compinfo=PyHaier.GetCompInfo(R241)
                #0.0002777778
                kwhnow=float(float(compinfo[2])*float(compinfo[3])/1000*float(kwhnowcorr))
                if str(statusdict['threeway']['value']) == 'DHW':
                    dhwkwhpd=float(statusdict['dhwkwhpd']['value'])+kwhnow
                    ischanged("dhwkwhpd", dhwkwhpd)
                elif str(statusdict['threeway']['value']) == "CH":
                    chkwhpd=float(statusdict['chkwhpd']['value'])+kwhnow
                    ischanged("chkwhpd",chkwhpd)
                fans=PyHaier.GetFanRpm(R241)
                pdps=PyHaier.GetPdPs(R241)
                eevlevel=PyHaier.GetEEVLevel(R241)
                tsatpd=PyHaier.GetTSatPd(R241)
                tsatps=PyHaier.GetTSatPs(R241)
                tao=PyHaier.GetTao(R241)
                ischanged("tdts", tdts)
                tdchart.append(tdts[0])
                tschart.append(tdts[1])
                factchart.append(compinfo[0])
                fsetchart.append(compinfo[1])
                ischanged("archerror", archerror)
                ischanged("compinfo", compinfo)
                ischanged("pdps", pdps)
                ischanged("eevlevel",eevlevel)
                ischanged("tsatpd",tsatpd)
                ischanged("tsatps",tsatps)
                pdsetchart.append(pdps[0])
                pdactchart.append(pdps[1])
                pssetchart.append(pdps[2])
                psactchart.append(pdps[3])
                eevlevelchart.append(eevlevel)
                tsatpdsetchart.append(tsatpd[0])
                tsatpdactchart.append(tsatpd[1])
                tsatpssetchart.append(tsatps[0])
                tsatpsactchart.append(tsatps[1])
                ischanged("fans", fans)
                ischanged("tao", tao)
                taochart.append(tao)
            if len(R101) == 6:
                dhw=PyHaier.GetDHWTemp(R101)
                ischanged("dhw", dhw)
                powerstate=PyHaier.GetState(R101)
                if 'Heat' in powerstate:
                    ischanged("pch", "on")
                else:
                    ischanged("pch", "off")
                if 'Cool' in powerstate:
                    ischanged("pcool", "on")
                else:
                    ischanged("pcool", "off")
                if not any(substring in powerstate for substring in ["Cool", "Heat"]):
                    if use_mqtt == "1":
                        client.publish(mqtt_topic + "/mode/state", "off")
                if 'Tank' in powerstate:
                    ischanged("pdhw", "on")
                else:
                    ischanged("pdhw", "off")
            ischanged("intemp", GetInsideTemp(insidetemp))
            ischanged("outtemp", GetOutsideTemp(outsidetemp))
            ischanged("humid", GetHumidity(humidity))
            scheduler()
            intempchart.append(statusdict['intemp']['value'])
            outtempchart.append(statusdict['outtemp']['value'])
            humidchart.append(statusdict['humid']['value'])
            hcurvechart.append(statusdict['hcurve']['value'])
            threeway=statusdict['threeway']['value']
            compinfo=statusdict['compinfo']['value']
            preset=statusdict['mode']['value']
            flimit=statusdict['flimit']['value']
            antionoff=statusdict['antionoff']['value']
            flimiton=GPIO.input(freqlimitpin)
            ischanged("flimiton", flimiton)
            flimitonchart.append(statusdict['flimiton']['value']*2)
        
            if len(compinfo) > 0:
                if dhwwl == "1" and compinfo[0] > 0 and threeway == "DHW" and (flimiton == "1" or preset != "turbo"):
                    logging.info("DHWWL Function ON")
                    flimitchange("0")
                    new_presetchange("turbo")
 
            socketlocal.emit("chart_update", {'datechart': str(now), 'tankchart': tank, 'twichart': twitwo[0], 'twochart': twitwo[1], 'thichart': thitho[0], 'thochart': thitho[1], 'taochart': tao, 'tdchart': tdts[0], 'tschart': tdts[1], 'pdsetchart': pdps[0], 'pdactchart': pdps[1], 'pssetchart': pdps[2], 'psactchart': pdps[3], 'intempchart': statusdict['intemp']['value'], 'outtempchart': statusdict['outtemp']['value'], 'humidchart': statusdict['humid']['value'], 'hcurvechart': statusdict['hcurve']['value'], 'factchart': compinfo[0], 'fsetchart': compinfo[1], 'flimitonchart': statusdict['flimiton']['value']*2, 'modechart_quiet': mode_q, 'modechart_eco': mode_e, 'modechart_turbo': mode_t })
        """
    # Snapshot pełnego statusu co 30s (do logu), niezależnie od ischanged()
    log_status_snapshot(30)

# Snapshot statusdict co 30s (pełny stan w jednej linii), bez udawania "has changed"
_last_snapshot_ts = 0

def log_status_snapshot(interval_s=30):
    global _last_snapshot_ts
    now = time.time()
    if now - _last_snapshot_ts < interval_s:
        return
    _last_snapshot_ts = now

    try:
        snap = {k: v.get("value", "N.A.") for k, v in statusdict.items()}
        logging.info("status_snapshot: %s", json.dumps(snap, ensure_ascii=False, separators=(",", ":"), default=str))
    except Exception as e:
        logging.error(f"Error in log_status_snapshot: {e}")

def gen_charts(hours=12):
    fromwhen=8640-(hours*60)
    chartdate=list(islice(datechart, fromwhen, None))
    charttank=list(islice(tankchart, fromwhen, None))
    charttwi=list(islice(twichart, fromwhen, None))
    charttwo=list(islice(twochart, fromwhen, None))
    chartthi=list(islice(thichart, fromwhen, None))
    charttho=list(islice(thochart, fromwhen, None))
    charttao=list(islice(taochart, fromwhen, None))
    charttd=list(islice(tdchart, fromwhen, None))
    chartts=list(islice(tschart, fromwhen, None))
    chartpdset=list(islice(pdsetchart, fromwhen, None))
    chartpdact=list(islice(pdactchart, fromwhen, None))
    chartpsset=list(islice(pssetchart, fromwhen, None))
    chartpsact=list(islice(psactchart, fromwhen, None))
    chartintemp=list(islice(intempchart, fromwhen, None))
    chartouttemp=list(islice(outtempchart, fromwhen, None))
    charthumid=list(islice(humidchart, fromwhen, None))
    charthcurve=list(islice(hcurvechart, fromwhen, None))
    chartfact=list(islice(factchart, fromwhen, None))
    chartfset=list(islice(fsetchart, fromwhen, None))
    chartflimiton=list(islice(flimitonchart, fromwhen, None))
    chartmode_quiet = list(islice(modechart_quiet, fromwhen, None))
    chartmode_eco = list(islice(modechart_eco, fromwhen, None))
    chartmode_turbo = list(islice(modechart_turbo, fromwhen, None))
    chartthreeway = list(islice(threewaychart, fromwhen, None))
    # Obliczanie wartości Przegrzania i Przechłodzenia
    chartsuperheat = []
    chartsubcooling = []
    for i in range(len(chartts)):
        # Sprawdzanie, czy wartości są puste, jeśli tak, przypisujemy domyślną wartość (np. 0)
        chartts_value = chartts[i] if chartts[i] != '' else '0'
        tsatpsactchart_value = tsatpsactchart[i] if tsatpsactchart[i] != '' else '0'
        tsatpdactchart_value = tsatpdactchart[i] if tsatpdactchart[i] != '' else '0'
        chartthi_value = chartthi[i] if chartthi[i] != '' else '0'

    # Obliczenia superheat i subcooling z wartościami bezwzględnymi
    # Przegrzanie = Ts − TSatPs
    # Dochłodzenie = TSatPd - Thi
        superheat = abs(float(chartts_value) - float(tsatpsactchart_value))
        subcooling = abs(float(tsatpdactchart_value) - float(chartthi_value))

        chartsuperheat.append(superheat)
        chartsubcooling.append(subcooling)

        return chartdate, charttank, charttwi, charttwo, chartthi, charttho, charttao, charttd, chartts, chartpdset, chartpdact, chartpsset, chartpsact, chartintemp, chartouttemp, charthumid, charthcurve, chartfact, chartfset, chartflimiton, chartmode_quiet, chartmode_eco, chartmode_turbo, chartthreeway, chartsuperheat, chartsubcooling


def create_user(**data):
    """Creates user with encrypted password"""
    if "username" not in data or "password" not in data:
        raise ValueError(gettext("username and password are required."))

    # Hash the user password
    data["password"] = generate_password_hash(
        data.pop("password"), method="pbkdf2:sha256"
    )

    # Here you insert the `data` in your users database
    # for this simple example we are recording in a json file
    db_users = json.load(open("users.json"))
    # add the new created user to json
    db_users[data["username"]] = data
    # commit changes to database
    json.dump(db_users, open("users.json", "w"))
    #return data
    msg=gettext("Password changed")
    return msg

def background_function():
    print("Background function running!")

# Flask route
@app.route('/')
@login_required
def home():
    if firstrun == "1":
        return redirect("/settings", code=302)
    else:
        theme=statusdict['theme']['value']
        global outsidetemp
        return render_template('index.html', theme=theme, version=version, needrestart=needrestart, flimit=flimit, outsidetemp=outsidetemp, antionoff=antionoff, presetquiet=presetquiet, presetturbo=presetturbo, presetautochange=presetautochange, flimittemp=flimittemp)

@app.route('/curvecalc')
@login_required
def curvecalc_route():
    curve=curvecalc()
    return jsonify(msg=curve)

@app.route('/theme', methods=['POST'])
def theme_route():
    theme = request.form['theme']
    settheme(theme)
    return theme

@app.route('/get_json_data')
def get_json_route():
    return get_json_data()

@app.route('/backup')
def backup_route():
    try:
        subprocess.check_output("7zr a backup.7z config.ini schedule_*", shell=True).decode().rstrip('\n')
        return send_file('/opt/haier/backup.7z', download_name='backup.hpi')
    except Exception as e:
        return str(e)

@app.route('/restore', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            flash('File uploaded, please restart HaierPi service', 'success')
            subprocess.check_output("7zr e -aoa /opt/haier/"+filename+" /opt/haier config.ini schedule_ch.json schedule_dhw.json", shell=True).decode().rstrip('\n')
            return redirect('/', code=302)
    return render_template('upload.html')

@app.route('/charts', methods=['GET','POST'])
@login_required
def charts_route():
    return render_template('charts.html', version=version)

@app.route('/settings', methods=['GET','POST'])
@login_required
def settings():
    return render_template('settings.html', version=version)

@app.route('/parameters', methods=['GET','POST'])
@login_required
def parameters():
    theme=statusdict['theme']['value']
    return  render_template('parameters.html', version=version, theme=theme)

@app.route('/scheduler', methods=['GET','POST'])
@login_required
def scheduler_route():
    if request.method == 'POST':
        if "schedulech" in request.form:
            msg, state = schedule_write('ch', request.form['schedulech'])
            return jsonify(msg=msg, state=state)
        if "scheduledhw" in request.form:
            msg, state = schedule_write('dhw', request.form['scheduledhw'])
            return jsonify(msg=msg, state=state)

    schedule1 = open("schedule_ch.json", "r")
    schedule2 = open("schedule_dhw.json", "r")
    theme=statusdict['theme']['value']
    return  render_template('scheduler.html', ch=Markup(schedule1.read()), dhw=Markup(schedule2.read()), version=version, theme=theme)

@app.route('/statechange', methods=['POST'])
@login_required
def change_state_route():
    mode = request.form['mode']
    value = request.form['value']
    logging.info(f'{mode} - {value}')
    information = statechange(mode, value, "0")
    return information
@app.route('/modechange', methods=['POST'])
@login_required
def change_mode_route():
    newvalue = request.form['newmode']
    msg, response = new_presetchange(newvalue)
    code=b2s(response)
    return jsonify(msg=msg, state=code)

@app.route('/flrchange', methods=['POST'])
@login_required
def change_flimitrelay_route():
    newvalue = request.form['newmode']
    msg,state = flimitchange(newvalue)
    return jsonify(msg=msg, state=state)

@app.route('/tempchange', methods=['POST'])
@login_required
def change_temp_route():
    which = request.form['which']
    value = request.form['value']
    directly = request.form['directly']
    msg, response = new_tempchange(which,value,directly)
    code=b2s(response)
    socketlocal.emit("data_update", {'setpoint': value})
    return jsonify(msg=msg, state=code)

@app.route('/updatecheck')
def updatecheck_route():
    response = updatecheck()
    return response

@app.route('/restart', methods=['GET'])
@login_required
def restart_route():
    output = restart()
    return output

@app.route('/changepass', methods=['POST'])
@login_required
def change_pass_route():
    user = request.form['user']
    password = request.form['password']
    response = create_user(username=user, password=password)
    return jsonify(response)

@app.route('/getdata', methods=['GET'])
@login_required(basic=True)
def getdata_route():
    output = getdata()
    return output

@app.route('/getparams', methods=['GET'])
@login_required(basic=True)
def getparams_route():
    twitwo, thitho, tdts, archerror, compinfo, fans, pdps, eevlevel, tsatpd, tsatps, tao, pump, threeway, chkwhpd, dhwkwhpd, superheat, subcooling = getparams()
    return jsonify(
        twitwo=twitwo,
        thitho=thitho,
        tdts=tdts,
        archerror=archerror,
        compinfo=compinfo,
        fans=fans,
        pdps=pdps,
        eevlevel=eevlevel,
        tsatpd=tsatpd,
        tsatps=tsatps,
        tao=tao,
        pump=pump,
        threeway=threeway,
        chkwhpd=chkwhpd,
        dhwkwhpd=dhwkwhpd,
        superheat=superheat,
        subcooling=subcooling,
    )

@socketlocal.on('client')
def handle_client_message(data):
    global grestarted
    logging.info(data)
    if 'hpiapp' in data:
        hpiapp(data['hpiapp'])
    elif 'mode' in data:
        information = statechange(data['mode'], data['value'], "1")
        logging.info(information)
#        emit('return', {'info': 'ok', 'status': 'success'})
        emit("return", {'statechange': data['mode'], 'status': information })
    elif 'charts' in data:
        variables=['chartdate', 'charttank', 'charttwi', 'charttwo', 'chartthi', 'charttho', 'charttao', 'charttd', 'chartts', 'chartpdset', 'chartpdact', 'chartpsset', 'chartpsact', 'chartintemp', 'chartouttemp', 'charthumid', 'charthcurve', 'chartfact', 'chartfset', 'chartflimiton', 'chartmode_quiet', 'chartmode_eco', 'chartmode_turbo','chartthreeway', 'chartsuperheat', 'chartsubcooling']
        values=gen_charts(int(data['charts']))
        valname=dict(zip(variables, values))
        emit('charts', valname)

    if 'curvecalc' in data:
        logging.info(data)
        curve=curvecalc()
        emit('return', {'curvecalc': curve })
    if 'restarted' in data:
        grestarted = 0
    if 'tempchange' in data:
        msg, response = new_tempchange(data['tempchange'],data['value'],data['directly'])
        code=b2s(response)
        if data['tempchange'] == 'heat': 
            emit("data_update", {'setpoint': data['value']})
        emit("return", {'tempchange': msg, 'type': code})
        if chscheduler == "1" or dhwscheduler == "1":
            emit("return", {'tempchange': 'Masz wlaczony harmonogram, temperatura zostanie nadpisana wg harmonogramu', 'type': 'warning' })
    if 'settings' in data:
        try:
            for key,value in data['settings'].items():
                KEY1=f'{key.split("$")[0]}'
                KEY2=f'{key.split("$")[1]}'
                VAL=f'{value}'
                config[KEY1][KEY2] = str(VAL)
                with open('/opt/config.ini', 'w') as configfile:
                    config.write(configfile)
            emit('return', {'info': "Zapisano", 'status': 'success'})
            loadconfig()
        except:
            emit('return', {'info': 'Błąd zapisu', 'status': 'danger'})

@sio_remote.event
def error(data):
    logging.error(data)
    if 'message' in data:
        if data['message'] == "Unauthorized":
            socketlocal.emit('return', {'info': data['message'], 'status': 'danger'})
            hpiapp('disconnect')
@sio_remote.event
def command(data):
    logging.info(f"Received command: {data}")
    if 'get_scheduler' in data:
        logging.info("get_scheduler-----------------------------------------------------")
        schedule1 = open("schedule_ch.json", "r")
        schedule2 = open("schedule_dhw.json", "r")
        data={}
        sched={}
        sched['chsch'] = json.loads(schedule1.read())
        sched['dhwsch'] = json.loads(schedule2.read())
        data['scheduler']=sched
        sio_remote.emit('data_from_device', data)

    if 'settings' in data:
        try:
            for key,value in data['settings'].items():
                KEY1=f'{key.split("$")[0]}'
                KEY2=f'{key.split("$")[1]}'
                VAL=f'{value}'
                config[KEY1][KEY2] = str(VAL)
                with open('/opt/config.ini', 'w') as configfile:
                    config.write(configfile)
            sio_remote.emit('return_from_device', {'info': "Zapisano", 'status': 'success'})
            loadconfig()
        except:
            sio_remote.emit('return_from_device', {'info': 'Błąd zapisu', 'status': 'danger'})

    if 'get_charts' in data:
        variables=['chartdate', 'charttank', 'charttwi', 'charttwo', 'chartthi', 'charttho', 'charttao', 'charttd', 'chartts', 'chartpdset', 'chartpdact', 'chartpsset', 'chartpsact', 'chartintemp', 'chartouttemp', 'charthumid', 'charthcurve', 'chartfact', 'chartfset', 'chartflimiton', 'chartmode_quiet', 'chartmode_eco', 'chartmode_turbo', 'chartsuperheat', 'chartsubcooling']
        values=gen_charts(int(data['get_charts']))
        valname=dict(zip(variables, values))
        charts={"charts": valname}
        logging.info(f"------wielkosc pakietu: {len(json.dumps(valname))}")
        sio_remote.emit("data_from_device", charts)

    elif 'get_settings' in data:
        heatingcurve = config['SETTINGS']['heatingcurve']
        antionoff = config['SETTINGS']['antionoff']
        hpiconn = statusdict['hpiconn']['value']
        settings={"settings": {"SETTINGS$insidetemp": insidetemp,"SETTINGS$outsidetemp": outsidetemp,"SETTINGS$humidity": humidity,"SETTINGS$antionoff": antionoff,"SETTINGS$antionoffdeltatime": antionoffdeltatime,"SETTINGS$deltatempturbo": deltatempturbo,"SETTINGS$deltatempquiet": deltatempquiet,"SETTINGS$deltatempflimit": deltatempflimit,"SETTINGS$dhwwl": dhwwl,"SETTINGS$chscheduler": chscheduler, "SETTINGS$dhwscheduler": dhwscheduler,"SETTINGS$flimit": flimit,"SETTINGS$flimittemp": flimittemp,"SETTINGS$presetautochange": presetautochange,"SETTINGS$presetquiet": presetquiet,"SETTINGS$presetturbo": presetturbo,"SETTINGS$heatingcurve": heatingcurve,"MAIN$heizfreq": timeout,"SETTINGS$hcslope": slope,"SETTINGS$hcpshift": pshift,"SETTINGS$hcamp": hcamp,"SETTINGS$hcman": hcman,"HOMEASSISTANT$HAADDR": haaddr,"HOMEASSISTANT$HAPORT": haport,"HOMEASSISTANT$KEY": hakey,"HOMEASSISTANT$ha_mqtt_discovery": ha_mqtt_discovery,"HOMEASSISTANT$insidesensor": insidesensor,"HOMEASSISTANT$outsidesensor": outsidesensor,"HOMEASSISTANT$humiditysensor": humiditysensor,"MQTT$mqtt": use_mqtt,"MQTT$address": mqtt_broker_addr,"MQTT$port": mqtt_broker_port,"MQTT$mqtt_ssl": mqtt_ssl,"MQTT$main_topic": mqtt_topic,"MQTT$username": mqtt_username,"MQTT$password": mqtt_password,"MAIN$bindaddress": bindaddr,"MAIN$bindport": bindport,"MAIN$modbusdev": modbusdev,"GPIO$modbus": modbuspin,"GPIO$freqlimit": freqlimitpin,"GPIO$heatdemand": heatdemandpin,"GPIO$cooldemand": cooldemandpin, "HPIAPP$hpikey":hpikey,"HPIAPP$hpiatstart":hpiatstart ,"hpiconn":hpiconn}}
        sio_remote.emit("data_from_device", settings)
    #if 'restarted' in data:
    #    grestarted = 0
    if 'mode' in data:
        response = statechange(data['mode'], data['value'], "1")
        sio_remote.emit("return_from_device", {'statechange': data['mode'], 'status': response })
    if 'tempchange' in data:
        msg, response = new_tempchange(data['tempchange'],data['value'],data['directly'])
        code=b2s(response)
        if data['tempchange'] == 'heat':
            sio_remote.emit("data_from_device", {'setpoint': data['value']})
        sio_remote.emit("return_from_device", {'tempchange': msg, 'type': code})
        if chscheduler == "1" or dhwscheduler == "1":
            sio_remote.emit("return_from_device", {'tempchange': 'Masz wlaczony harmonogram, temperatura zostanie nadpisana wg harmonogramu', 'type': 'warning' })
    if 'curvecalc' in data:
        logging.info(data)
        curve=curvecalc()
        sio_remote.emit('return_from_device', {'curvecalc': curve })

    if 'get_data' in data:
        heatdemand = GPIO.input(heatdemandpin)
        cooldemand = GPIO.input(cooldemandpin)
        flimiton_gpio = GPIO.input(freqlimitpin)
        flrelay = flimiton_gpio
        
        restarted = grestarted
        intemp=statusdict['intemp']['value']
        outtemp=statusdict['outtemp']['value']
        setpoint=statusdict['settemp']['value']
        hcurve=statusdict['hcurve']['value']
        dhw=statusdict['dhw']['value']
        tank=statusdict['tank']['value']
        mode=statusdict['mode']['value']
        humid=statusdict['humid']['value']
        pch=statusdict['pch']['value']
        pdhw=statusdict['pdhw']['value']
        pcool=statusdict['pcool']['value']
        presetch = presetautochange
        
        ltemp = flimittemp
        fflimit = flimit
        heatingcurve = config['SETTINGS']['heatingcurve']
        antionoff = config['SETTINGS']['antionoff']
        isr241=1
        isr141=1
        while (isr241):
            if (len(R241) == 22):
                tdts=PyHaier.GetTdTs(R241)
                archerror=PyHaier.GetArchError(R241)
                compinfo=PyHaier.GetCompInfo(R241)
                fans=PyHaier.GetFanRpm(R241)
                pdps=PyHaier.GetPdPs(R241)
                eevlevel=PyHaier.GetEEVLevel(R241)
                tsatpd=PyHaier.GetTSatPd(R241)
                tsatps=PyHaier.GetTSatPs(R241)
                tao=PyHaier.GetTao(R241)
                isr241=0
        while (isr141):
            if (len(R141) == 16):
                twitwo = PyHaier.GetTwiTwo(R141)
                thitho = PyHaier.GetThiTho(R141)
                pump=PyHaier.GetPump(R141)
                threeway=PyHaier.Get3way(R141)
                isr141=0
        chkwhpd=statusdict['chkwhpd']['value']
        dhwkwhpd=statusdict['dhwkwhpd']['value']
        dtquiet=deltatempquiet
        dtflimit=deltatempflimit
        dtturbo=deltatempturbo
        aoodt=antionoffdeltatime
        
        # --- statusdict ---
        ischanged("heatdemand", heatdemand)
        ischanged("cooldemand", cooldemand)
        ischanged("flimiton", flimiton_gpio)
        ischanged("flrelay", flrelay)
        ischanged("pch", pch)
        ischanged("pcool", pcool)
        ischanged("pdhw", pdhw)

        # delta temps
        ischanged("deltatempturbo", dtturbo)
        ischanged("deltatempquiet", dtquiet)
        ischanged("deltatempflimit", dtflimit)

        # R241
        ischanged("tdts", tdts)
        ischanged("archerror", archerror)
        ischanged("compinfo", compinfo)
        ischanged("fans", fans)
        ischanged("pdps", pdps)
        ischanged("eevlevel", eevlevel)
        ischanged("tsatpd", tsatpd)
        ischanged("tsatps", tsatps)
        ischanged("tao", tao)

        # R141
        ischanged("twitwo", twitwo)
        ischanged("thitho", thitho)
        ischanged("pump", pump)
        ischanged("threeway", threeway)
        update_defrost_state()

        # liczniki
        ischanged("chkwhpd", chkwhpd)
        ischanged("dhwkwhpd", dhwkwhpd)

        
        for name in list(locals().keys()):
            sio_emit={'data_update': {name: locals()[name]}}
            sio_remote.emit('data_from_device', sio_emit)
            #sio_remote.emit("data_from_device", data)


@socketlocal.on('connect')
def handle_connect():
    referer = request.headers.get("Referer")
    if 'charts' in referer:
        variables=['chartdate', 'charttank', 'charttwi', 'charttwo', 'chartthi', 'charttho', 'charttao', 'charttd', 'chartts', 'chartpdset', 'chartpdact', 'chartpsset', 'chartpsact', 'chartintemp', 'chartouttemp', 'charthumid', 'charthcurve', 'chartfact', 'chartfset', 'chartflimiton', 'chartmode_quiet', 'chartmode_eco', 'chartmode_turbo','chartthreeway', 'chartsuperheat', 'chartsubcooling']
        values=gen_charts()
        valname=dict(zip(variables, values))
        emit('charts', valname)

    elif 'scheduler' in referer:
        schedule1 = open("schedule_ch.json", "r")
        schedule2 = open("schedule_dhw.json", "r")
        data={}
        data['chsch'] = json.loads(schedule1.read())
        data['dhwsch'] = json.loads(schedule2.read())
        emit('scheduler', data)
    elif 'settings' in referer:
        heatingcurve = config['SETTINGS']['heatingcurve']
        antionoff = config['SETTINGS']['antionoff']
        hpiconn = statusdict['hpiconn']['value']
        settings={"SETTINGS$insidetemp": insidetemp,"SETTINGS$outsidetemp": outsidetemp,"SETTINGS$humidity": humidity,"SETTINGS$antionoff": antionoff,"SETTINGS$antionoffdeltatime": antionoffdeltatime,"SETTINGS$deltatempturbo": deltatempturbo,"SETTINGS$deltatempquiet": deltatempquiet,"SETTINGS$deltatempflimit": deltatempflimit,"SETTINGS$dhwwl": dhwwl,"SETTINGS$chscheduler": chscheduler, "SETTINGS$dhwscheduler": dhwscheduler,"SETTINGS$flimit": flimit,"SETTINGS$flimittemp": flimittemp,"SETTINGS$presetautochange": presetautochange,"SETTINGS$presetquiet": presetquiet,"SETTINGS$presetturbo": presetturbo,"SETTINGS$heatingcurve": heatingcurve,"MAIN$heizfreq": timeout,"SETTINGS$hcslope": slope,"SETTINGS$hcpshift": pshift,"SETTINGS$hcamp": hcamp,"SETTINGS$hcman": hcman,"HOMEASSISTANT$HAADDR": haaddr,"HOMEASSISTANT$HAPORT": haport,"HOMEASSISTANT$KEY": hakey,"HOMEASSISTANT$ha_mqtt_discovery": ha_mqtt_discovery,"HOMEASSISTANT$insidesensor": insidesensor,"HOMEASSISTANT$outsidesensor": outsidesensor,"HOMEASSISTANT$humiditysensor": humiditysensor,"MQTT$mqtt": use_mqtt,"MQTT$address": mqtt_broker_addr,"MQTT$port": mqtt_broker_port,"MQTT$mqtt_ssl": mqtt_ssl,"MQTT$main_topic": mqtt_topic,"MQTT$username": mqtt_username,"MQTT$password": mqtt_password,"MAIN$bindaddress": bindaddr,"MAIN$bindport": bindport,"MAIN$modbusdev": modbusdev,"GPIO$modbus": modbuspin,"GPIO$freqlimit": freqlimitpin,"GPIO$heatdemand": heatdemandpin,"GPIO$cooldemand": cooldemandpin, "HPIAPP$hpikey":hpikey,"HPIAPP$hpiatstart":hpiatstart ,"hpiconn":hpiconn}
        emit('settings', settings)
    else:
        restarted = grestarted
        hpiconn=statusdict['hpiconn']['value']
        flimiton=statusdict['flimiton']['value']
        intemp=statusdict['intemp']['value']
        outtemp=statusdict['outtemp']['value']
        setpoint=statusdict['settemp']['value']
        hcurve=statusdict['hcurve']['value']
        dhw=statusdict['dhw']['value']
        tank=statusdict['tank']['value']
        mode=statusdict['mode']['value']
        humid=statusdict['humid']['value']
        pch=statusdict['pch']['value']
        pdhw=statusdict['pdhw']['value']
        pcool=statusdict['pcool']['value']
        presetch = presetautochange
        heatdemand=GPIO.input(heatdemandpin)
        cooldemand=GPIO.input(cooldemandpin)
        flimiton=GPIO.input(freqlimitpin)
        ltemp = flimittemp
        fflimit = flimit
        heatingcurve = config['SETTINGS']['heatingcurve']
        antionoff = config['SETTINGS']['antionoff']
        isr241=1
        isr141=1
        while (isr241):
            if (len(R241) == 22):
                tdts=PyHaier.GetTdTs(R241)
                archerror=PyHaier.GetArchError(R241)
                compinfo=PyHaier.GetCompInfo(R241)
                fans=PyHaier.GetFanRpm(R241)
                pdps=PyHaier.GetPdPs(R241)
                eevlevel=PyHaier.GetEEVLevel(R241)
                tsatpd=PyHaier.GetTSatPd(R241)
                tsatps=PyHaier.GetTSatPs(R241)
                tao=PyHaier.GetTao(R241)
                isr241=0
        while (isr141):
            if (len(R141) == 16):
                twitwo = PyHaier.GetTwiTwo(R141)
                thitho = PyHaier.GetThiTho(R141)
                pump=PyHaier.GetPump(R141)
                threeway=PyHaier.Get3way(R141)
                isr141=0
        chkwhpd=statusdict['chkwhpd']['value']
        dhwkwhpd=statusdict['dhwkwhpd']['value']
        dtquiet=deltatempquiet
        dtflimit=deltatempflimit
        dtturbo=deltatempturbo
        aoodt=antionoffdeltatime
        for name in list(locals().keys()):
            emit('data_update', {name: locals()[name]})


# Function to run the background function using a scheduler
def run_background_function():
    job = every(30).seconds.do(GetParameters)
    job2 = every(int(timeout)).minutes.do(curvecalc)
    while True:
        run_pending()
        time.sleep(1)
        if event.is_set():
            break

def connect_mqtt():
    client.on_connect = on_connect  # Define callback function for successful connection
    client.on_message = on_message  # Define callback function for receipt of a message
    client.on_disconnect = on_disconnect
    client.will_set(mqtt_topic + "/connected","offline",qos=1,retain=False)
    if mqtt_ssl == '1':
        client.tls_set(tls_version=mqtt.ssl.PROTOCOL_TLS)
    client.username_pw_set(mqtt_username, mqtt_password)
    try:
        client.connect(mqtt_broker_addr, int(mqtt_broker_port))
    except:
        logging.error(colored("MQTT connection error.","red", attrs=['bold']))
    client.loop_forever()  # Start networking daemon

def configure_ha_mqtt_discovery():

    def configure_sensor(name, status_topic, unique_id, unit, device_class, state_class, template):
        jsonMsg = {
            "name" : name,
            "stat_t" : status_topic,
            "uniq_id" : unique_id,
            "unit_of_meas" : unit,
            "stat_cla" : state_class,
            "exp_aft" : "0",
            "dev" : {
                "name" : "HaierPi",
                "ids" : "HaierPi",
                "cu" : f"http://{ip_address}:{bindport}",
                "mf" : "ktostam",
                "mdl" : "HaierPi",
                "sw" : version
            } 
        }
        
        if unit is not None:
            jsonMsg["unit"] = unit
        if device_class is not None:
            jsonMsg["dev_cla"] = device_class    
        if state_class is not None:
            jsonMsg["stat_cla"] = state_class
        if template is not None:
            jsonMsg["value_template"] = template
        msg = json.dumps(jsonMsg)
        
        client.publish(ha_mqtt_discovery_prefix+f"/sensor/HaierPi/{unique_id}/config", msg, qos=1)

    def configure_number(name, command_topic, status_topic, unique_id, unit, min, max, device_class):
        msg = json.dumps(
            {
                "name" : name,
                "cmd_t" : command_topic,
                "stat_t" : status_topic,
                "uniq_id" : unique_id,
                "unit_of_meas" : unit,
                "min" : min,
                "max" : max,
                "mode" : "slider",
                "step" : "0.1",
                "dev_cla" : device_class,
                "dev" : {
                    "name" : "HaierPi",
                    "ids" : "HaierPi",
                    "cu" : f"http://{ip_address}:{bindport}",
                    "mf" : "ktostam",
                    "mdl" : "HaierPi",
                    "sw" : version
                }
            }
        )
        
        client.publish(ha_mqtt_discovery_prefix + f"/number/HaierPi/{unique_id}/config", msg, qos=1)
        
    def configure_select(name, command_topic, status_topic, unique_id, options):
        msg = json.dumps(
            {
                "name" : name,
                "cmd_t" : command_topic,
                "stat_t" : status_topic,
                "uniq_id" : unique_id,
                "options" : options,
                "dev" : {
                    "name" : "HaierPi",
                    "ids" : "HaierPi",
                    "cu" : f"http://{ip_address}:{bindport}",
                    "mf" : "ktostam",
                    "mdl" : "HaierPi",
                    "sw" : version
                }
            }
        )
        
        client.publish(ha_mqtt_discovery_prefix + f"/select/HaierPi/{unique_id}/config", msg, qos=1)
        
    

    def configure_binary_sensor(name, status_topic, unique_id, device_class=None, template=None, payload_on="on", payload_off="off"):
        jsonMsg = {
            "name": name,
            "stat_t": status_topic,
            "uniq_id": unique_id,
            "payload_on": payload_on,
            "payload_off": payload_off,
            "exp_aft": "0",
            "dev": {
                "name": "HaierPi",
                "ids": "HaierPi",
                "cu": f"http://{ip_address}:{bindport}",
                "mf": "ktostam",
                "mdl": "HaierPi",
                "sw": version
            }
        }
        if device_class is not None:
            jsonMsg["dev_cla"] = device_class
        if template is not None:
            jsonMsg["value_template"] = template

        client.publish(ha_mqtt_discovery_prefix + f"/binary_sensor/HaierPi/{unique_id}/config", json.dumps(jsonMsg), qos=1)
    logging.info("Configuring HA discovery")

    configure_number("Set temp", mqtt_topic + "/temperature/set", mqtt_topic + "/temperature/state","HaierPi_SetTemp","°C", 0.0, 50.0, "temperature")
    configure_select("Preset", mqtt_topic + "/preset_mode/set", mqtt_topic + "/preset_mode/state", "Haier_Preset", ["eco", "quiet", "turbo"])
    configure_sensor("Heating curve value",mqtt_topic + "/heatcurve","HaierPi_Heatcurve","°C", "temperature","measurement",None)
    configure_sensor("DHW set temperature",mqtt_topic + "/dhw/temperature/state","HaierPi_DHWSet","°C", "temperature","measurement",None)
    configure_sensor("DHW actual temperature",mqtt_topic + "/dhw/curtemperature/state","HaierPi_DHWCurrent","°C", "temperature","measurement",None)
    configure_sensor("Outside temperature",mqtt_topic + "/outtemp/state","HaierPi_OutsideTemp", "°C", "temperature", "measurement", None)
    configure_sensor("Inside temperature",mqtt_topic + "/intemp/state","HaierPi_InsideTemp", "°C", "temperature", "measurement", None)
    configure_sensor("Humidity inside",mqtt_topic + "/humidity/state","HaierPi_HumidityInside","%", "humidity","measurement",None)
    configure_sensor("3-way valve",mqtt_topic + "/details/threeway/state","HaierPi_3wayvalve", None, None, None, None)
    configure_sensor("Pump",mqtt_topic + "/details/pump/state","HaierPi_Pump", None, None, None, None)
    configure_sensor("Archerror",mqtt_topic + "/details/archerror/state","HaierPi_Archerror", None, None, None, None)
    configure_sensor("Mode",mqtt_topic + "/mode/state","HaierPi_Mode", None, None, None, None)
    configure_select("Mode", mqtt_topic + "/mode/set", mqtt_topic + "/mode/state", "HaierPi_Mode", ["off", "heat", "cool"])
    configure_sensor("DHW Mode",mqtt_topic + "/dhw/mode/state","HaierPi_DHWMode", None, None, None, None)
    configure_select("DHW Mode", mqtt_topic + "/dhw/mode/set", mqtt_topic + "/dhw/mode/state", "HaierPi_DHWMode", ["off", "heat"])
    configure_sensor("Tao",mqtt_topic + "/details/tao/state","HaierPi_Tao","°C", "temperature","measurement", None)
    configure_sensor("Tdef",mqtt_topic + "/details/tdef/state","HaierPi_Tdef","°C", "temperature","measurement", None)
    configure_sensor("Twi",mqtt_topic + "/details/twitwo/state","HaierPi_Twi","°C", "temperature","measurement", "{{ value_json[0] | float}}")
    configure_sensor("Two",mqtt_topic + "/details/twitwo/state","HaierPi_Two","°C", "temperature","measurement", "{{ value_json[1] | float}}")
    configure_sensor("Thi",mqtt_topic + "/details/thitho/state","HaierPi_Thi","°C", "temperature","measurement", "{{ value_json[0] | float}}")
    configure_sensor("Tho",mqtt_topic + "/details/thitho/state","HaierPi_Tho","°C", "temperature","measurement", "{{ value_json[1] | float}}")
    configure_sensor("Fan 1",mqtt_topic + "/details/fans/state","HaierPi_Fan1","rpm", None, "measurement", "{{ value_json[0] | float}}")
    configure_sensor("Fan 2",mqtt_topic + "/details/fans/state","HaierPi_Fan2","rpm", None, "measurement", "{{ value_json[1] | float}}")
    configure_sensor("Pdset",mqtt_topic + "/details/pdps/state","HaierPi_Pd_set","Bar", "pressure","measurement", "{{ value_json[0] | float}}")
    configure_sensor("Pdact",mqtt_topic + "/details/pdps/state","HaierPi_Pd_act","Bar", "pressure","measurement", "{{ value_json[1] | float}}")
    configure_sensor("Psset",mqtt_topic + "/details/pdps/state","HaierPi_Ps_set","Bar", "pressure","measurement", "{{ value_json[2] | float}}")
    configure_sensor("Psact",mqtt_topic + "/details/pdps/state","HaierPi_Ps_act","Bar", "pressure","measurement", "{{ value_json[3] | float}}")
    configure_sensor("TSatPdset",mqtt_topic + "/details/tsatpd/state","HaierPi_TSatPd_set","°C", "temperature","measurement", "{{ value_json[0] | float}}")
    configure_sensor("TSatPdact",mqtt_topic + "/details/tsatpd/state","HaierPi_TSatPd_act","°C", "temperature","measurement", "{{ value_json[1] | float}}")
    configure_sensor("TSatPsset",mqtt_topic + "/details/tsatps/state","HaierPi_TSatPs_set","°C", "temperature","measurement", "{{ value_json[0] | float}}")
    configure_sensor("TSatPsact",mqtt_topic + "/details/tsatps/state","HaierPi_TSatPs_act","°C", "temperature","measurement", "{{ value_json[1] | float}}")
    configure_sensor("Heatdemand", mqtt_topic + "/details/heatdemand/state", "HaierPi_HeatDemand", None, None, "measurement", "{{ value_json | float }}")
    configure_sensor("Cooldemand", mqtt_topic + "/details/cooldemand/state","HaierPi_CoolDemand", None, None, None, "{{ value | float }}")
    configure_sensor("Superheat", mqtt_topic + "/details/superheat/state","HaierPi_Superheat","°C", "temperature","measurement", None)
    configure_sensor("Subcooling", mqtt_topic + "/details/subcooling/state","HaierPi_Subcooling","°C", "temperature","measurement", None)
    configure_sensor("FLrelay", mqtt_topic + "/details/flrelay/state", "HaierPi_FLRelay", None, None, None, "{{ value | int }}")
    configure_sensor("Anty On-OFF Delta", mqtt_topic + "/details/delta/state", "HaierPi_Delta", "°C", "temperature", "measurement", "{{ value_json | float }}")
    configure_sensor("Delta Temp FLimit", mqtt_topic + "/details/deltatempflimit/state", "HaierPi_DeltaTempFLimit", "°C", "temperature", "measurement", "{{ value_json | float }}")
    configure_sensor("Delta Temp Quiet", mqtt_topic + "/details/deltatempquiet/state", "HaierPi_DeltaTempQuiet", "°C", "temperature", "measurement", "{{ value_json | float }}")
    configure_sensor("Delta Temp Turbo", mqtt_topic + "/details/deltatempturbo/state", "HaierPi_DeltaTempTurbo", "°C", "temperature", "measurement", "{{ value_json | float }}")
    configure_sensor("Delta Temp Eco", mqtt_topic + "/details/deltatempeco/state", "HaierPi_DeltaTempEco", "°C", "temperature", "measurement", "{{ value_json | float }}")
    configure_sensor("Anti On-Off Delta Time", mqtt_topic + "/details/antionoffdeltatime/state", "HaierPi_AntiOnOffDeltaTime", "min", "duration", "measurement", "{{ value_json | float }}")
    configure_sensor("Compressor fact",mqtt_topic + "/details/compinfo/state","HaierPi_Compfact","Hz", "frequency","measurement", "{{ value_json[0] | float}}")
    configure_sensor("Compressor fset",mqtt_topic + "/details/compinfo/state","HaierPi_Compfset","Hz", "frequency","measurement", "{{ value_json[1] | float}}")
    configure_sensor("Compressor current",mqtt_topic + "/details/compinfo/state","HaierPi_Compcurrent","A", "current","measurement", "{{ value_json[2] | float}}")
    configure_sensor("Compressor voltage",mqtt_topic + "/details/compinfo/state","HaierPi_Compvoltage","V", "voltage","measurement", "{{ value_json[3] | float}}")
    configure_sensor("Compressor temperature",mqtt_topic + "/details/compinfo/state","HaierPi_Comptemperature","°C", "temperature","measurement", "{{ value_json[4] | float}}")
    configure_sensor("Td",mqtt_topic + "/details/tdts/state","HaierPi_Td","°C", "temperature","measurement","{{ value_json[0] | float}}")
    configure_sensor("Ts",mqtt_topic + "/details/tdts/state","HaierPi_Ts","°C", "temperature","measurement","{{ value_json[1] | float}}")
    configure_sensor("Daily CH energy usage", mqtt_topic +"/details/chkwhpd","HaierPi_CH_daily_kWh", "kWh", "energy", "measurement", None)
    configure_sensor("Daily DHW energy usage", mqtt_topic +"/details/dhwkwhpd","HaierPi_DHW_daily_kWh", "kWh", "energy", "measurement", None)
    configure_sensor("EEV level",mqtt_topic + "/details/eevlevel/state","HaierPi_EEVLevel", None, None, "measurement","{{ value | float }}")
    configure_binary_sensor("PCH", mqtt_topic + "/details/pch/state", "HaierPi_PCH")
    configure_binary_sensor("PCool", mqtt_topic + "/details/pcool/state", "HaierPi_PCool")
    configure_binary_sensor("PDHW", mqtt_topic + "/details/pdhw/state", "HaierPi_PDHW")
    configure_binary_sensor("FLimitOn", mqtt_topic + "/details/flimiton/state", "HaierPi_FLimitOn", payload_on="1", payload_off="0")
    configure_binary_sensor("Defrost", mqtt_topic + "/details/defrost/state", "HaierPi_Defrost")

def threads_check():
    global dead
    while True:
        if not bg_thread.is_alive():
            if dead == 0:
                logging.error("Background thread DEAD")

                dead = 1
        elif not serial_thread.is_alive():
            if dead == 0:
                logging.error("Serial Thread DEAD")
                dead = 1
        elif use_mqtt == "1":
            if not mqtt_bg.is_alive():
                if dead == 0:
                    logging.error("MQTT thread DEAD")
                    dead = 1
        if dead == 1:
            now = datetime.now()
            crash_date=now.strftime("%Y-%m-%d_%H-%M-%S")
            proc = subprocess.Popen(['journalctl', '-t', 'HaierPi', '-p','debug'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            f=open("/opt/haier/crashlog-"+crash_date+".log", "w")
            for line in iter(proc.stdout.readline, ''):
                f.write(line)
            f.close()
            with open("/opt/haier/crashlog-"+crash_date+".log", "r") as f:
                files = {"file": f}
                headers = {'Authorization': f"Bearer {hpikey}"}
                r=requests.post("https://app.haierpi.pl/upload", files=files, headers=headers)
            dead = 2

        time.sleep(1)
        if event.is_set():
            break
        #restart()

# Start the Flask app in a separate thread
babel.init_app(app, locale_selector=get_locale)
#babel.init_app(app)

if __name__ == '__main__':
    loadconfig()
    app.jinja_env.globals['get_locale'] = 'pl'
    logging.warning(colored(welcome,"yellow", attrs=['bold']))
    logging.warning(colored(f"Service running: http://{ip_address}:{bindport} ", "green"))
    logging.warning(f"MQTT: {'enabled' if use_mqtt == '1' else 'disabled'}")
    logging.warning(f"Home Assistant MQTT Discovery: {'enabled' if ha_mqtt_discovery == '1' and use_mqtt == '1' else 'disabled'}")
    signal.signal(signal.SIGINT, handler)
    bg_thread = threading.Thread(target=run_background_function, daemon=True)
    bg_thread.start()
    if use_mqtt == '1':
        client = mqtt.Client(mqtt_topic)  # Create instance of client
        mqtt_bg = threading.Thread(target=connect_mqtt, daemon=True)
        mqtt_bg.start()
        services.append(client)

    serial_thread = threading.Thread(target=ReadPump, daemon=True)
    serial_thread.start()
    threadcheck = threading.Thread(target=threads_check)
    threadcheck.start()
    #serve(socketio, host=bindaddr, port=bindport)
        #app.run(debug=False, host=bindaddr, port=bindport)#, ssl_context='adhoc')
    socketlocal.run(app, host=bindaddr, port=bindport, allow_unsafe_werkzeug=True, debug=False)
