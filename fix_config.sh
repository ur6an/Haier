#!/bin/bash
#set -euo pipefail

SERVICE="haier"
BASE_DIR="/opt/haier"
CONFIG="/opt/config.ini"
REPO="/opt/haier/config.ini.repo"

echo "Naprawiamy config"

systemctl stop "$SERVICE"

cd "$BASE_DIR"

echo
if [[ ! -f "$CONFIG" ]]; then
    echo "⚠️  Brak pliku config.ini, przywracanie config.ini"
    if [[ -f "$REPO" ]]; then
        cp "$REPO" "$CONFIG"
    else
        echo "❌ Brak pliku repo: $REPO"
        exit 1
    fi
fi

# -------------------------------------------------
# FUNKCJE
# -------------------------------------------------

config_has() {
    grep -Eq "^[[:space:]]*$1[[:space:]]*=" "$CONFIG"
}

insert_after_section() {
    local section="$1"
    local content="$2"
    local tmp
    tmp="$(mktemp)"

    awk -v sec="[$section]" -v txt="$content" '
    $0 == sec {
        print
        print txt
        next
    }
    { print }
    ' "$CONFIG" > "$tmp" && mv "$tmp" "$CONFIG"
}

# -------------------------------------------------
# Sprawdzanie czy wartości są puste
# -------------------------------------------------

if grep -Eq '^[[:space:]]*firstrun[[:space:]]*=[[:space:]]*$' "$CONFIG" && grep -Eq '^[[:space:]]*modbus[[:space:]]*=[[:space:]]*$' "$CONFIG"; then
    echo "⚠️  Brak wartości w pliku config.ini, przywracanie config.ini"
    if [[ -f "$REPO" ]]; then
        cp "$REPO" "$CONFIG"
    else
        echo "❌ Brak pliku repo: $REPO"
        exit 1
    fi
fi

# -------------------------------------------------
# Usuwanie wpisu blablabla = abccasd
# -------------------------------------------------

sed -i '/^[[:space:]]*blablabla[[:space:]]*=/d' "$CONFIG"

# -------------------------------------------------
# CWU
# -------------------------------------------------

if ! config_has "dhwuse"; then
    read -p "Czy korzystasz z CWU? [t/n]: " -n 1 answer < /dev/tty
    echo

    [[ "$answer" =~ [Tt] ]] && DHW=1 || DHW=0

    insert_after_section "SETTINGS" "dhwuse = $DHW"
    echo "ℹ️  Wpis dhwuse dodany"
else
    echo "ℹ️  Wpis dhwuse istnieje"
fi

# -------------------------------------------------
# ZONE
# -------------------------------------------------

if ! config_has "zone_frost_enable"; then
    insert_after_section "SETTINGS" \
"zone_frost_enable = 0
zone_frost_temp = -5
zone_frost_mode = quiet
zone_warm_enable = 0
zone_warm_temp = 10
zone_warm_mode = quiet_flimit"
    echo "ℹ️  Wpis zone dodany"
else
    echo "ℹ️  Wpis zone istnieje"
fi

# -------------------------------------------------
# EMERGENCY
# -------------------------------------------------

if ! config_has "emergency_intemp"; then
    insert_after_section "SETTINGS" "emergency_intemp = 20.0"
    echo "ℹ️  Wpis emergency_intemp dodany"
else
    echo "ℹ️  Wpis emergency_intemp istnieje"
fi

# -------------------------------------------------
# DHW TEMP
# -------------------------------------------------

if ! config_has "dhwtemp"; then
    insert_after_section "SETTINGS" "dhwtemp = builtin"
    insert_after_section "HOMEASSISTANT" "dhwsensor ="
    echo "ℹ️  Wpis dhwtemp dodany"
else
    echo "ℹ️  Wpis dhwtemp istnieje"
fi

# -------------------------------------------------
# NO LIMIT MODE
# -------------------------------------------------

if ! config_has "dhwnolimit_mode"; then
    insert_after_section "SETTINGS" "dhwnolimit_mode = turbo"
    echo "ℹ️  Wpis dhwnolimit_mode dodany"
else
    echo "ℹ️  Wpis dhwnolimit_mode istnieje"
fi

# -------------------------------------------------
# DIRECT THERMOSTAT
# -------------------------------------------------

if ! config_has "direct_thermostat"; then
    insert_after_section "SETTINGS" \
"direct_thermostat = 0
direct_inside_settemp = 22.0"
    echo "ℹ️  Wpis direct_thermostat dodany"
else
    echo "ℹ️  Wpis direct_thermostat istnieje"
fi

# -------------------------------------------------
# FIX
# -------------------------------------------------

read -p "Czy masz problem z logowaniem na strone www? [t/n]: " -n 1 answer < /dev/tty
echo

if [[ "$answer" =~ [Tt] ]]; then
    sed -i '/^[[:space:]]*bindport[[:space:]]*=/d' "$CONFIG"
    sed -i '/^[[:space:]]*bindaddress[[:space:]]*=/d' "$CONFIG"
    sed -i '/^[[:space:]]*firstrun[[:space:]]*=/d' "$CONFIG"
    sed -i '/^[[:space:]]*modbusdev[[:space:]]*=/d' "$CONFIG"
    sed -i '/^[[:space:]]*modbus[[:space:]]*=/d' "$CONFIG"
    sed -i '/^[[:space:]]*freqlimit[[:space:]]*=/d' "$CONFIG"
    sed -i '/^[[:space:]]*heatdemand[[:space:]]*=/d' "$CONFIG"
    sed -i '/^[[:space:]]*cooldemand[[:space:]]*=/d' "$CONFIG"
    insert_after_section "MAIN" "bindport = 80"
    insert_after_section "MAIN" "bindaddress = 0.0.0.0"
    insert_after_section "MAIN" "firstrun = 0"
    if grep -q "ARMv7" /proc/cpuinfo; then
        echo "✅ OK: Znalazłem SBC NanoPi NEO 1.4"
        insert_after_section "MAIN" "modbusdev = /dev/ttyS1"
        insert_after_section "GPIO" \
"modbus = 0
freqlimit = 64
heatdemand = 2
cooldemand = 3"
    elif grep -q "ARMv6" /proc/cpuinfo; then
        echo "✅ OK: Znalazłem SBC RaspberryPi zero W"
        insert_after_section "MAIN" "modbusdev = /dev/ttyAMA0"
        insert_after_section "GPIO" \
"modbus = 17
freqlimit = 27
heatdemand = 22
cooldemand = 10"
    else
        echo "⚠️ UWAGA: Nie znalazłem żadnej z wymaganych architektur (ARMv6 lub ARMv7)"
        exit 1
    fi
    echo "ℹ️  Wpisy w config naprawiono"
fi

# -------------------------------------------------
# START
# -------------------------------------------------

echo
echo "🚀 Startuję usługę Haier..."
systemctl start "$SERVICE" \
    && echo "✅ OK: USŁUGA WYSTARTOWAŁA" \
    || echo "⚠️  Błąd uruchamiania usługi"
