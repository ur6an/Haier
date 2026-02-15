#!/bin/bash
set -euo pipefail

SERVICE="haier"
BASE_DIR="/opt/haier"
CONFIG="/opt/config.ini"
TMP="$(mktemp)"

echo "📦 Wklejam pliki z paczki test fixV1.4.5.8"

systemctl stop "$SERVICE"

rm -rf "$BASE_DIR/static" "$BASE_DIR/templates" "$BASE_DIR/main.py"
cd "$BASE_DIR"

curl -sL https://github.com/ur6an/Haier/raw/refs/heads/main/fixV1.4.5.8.tar.gz | tar -xz

cp "$CONFIG" "${CONFIG}.backup"

echo "✅ Podmiana zakończona"
echo

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
    insert_after_section "SETTINGS" "direct_thermostat = 0"
    echo "ℹ️  Wpis direct_thermostat dodany"
else
    echo "ℹ️  Wpis direct_thermostat istnieje"
fi

# -------------------------------------------------
# DIRECT INSIDE SETTEMP
# -------------------------------------------------

if ! config_has "direct_inside_settemp"; then
    insert_after_section "SETTINGS" "direct_inside_settemp = 22.0"
    echo "ℹ️  Wpis direct_inside_settemp dodany"
else
    echo "ℹ️  Wpis direct_inside_settemp istnieje"
fi

# -------------------------------------------------
# UI_FONT
# -------------------------------------------------

if ! config_has "ui_font"; then
    insert_after_section "MAIN" "ui_font = inter"
    insert_after_section "SETTINGS" \
"antifreeze_custom_enable = 0
antifreeze_custom_outtemp = 1
antifreeze_custom_twi = 4
antifreeze_custom_two = 4
antifreeze_custom_runtime_min = 0.5
service_test_duration_s = 30
thermostat_on = 1
heatingcurve_last = manual"
    echo "ℹ️  Wpis ui_font dodany"
else
    echo "ℹ️  Wpis ui_font istnieje"
fi

# -------------------------------------------------
# START
# -------------------------------------------------

echo
echo "🚀 Startuję usługę Haier..."
systemctl start "$SERVICE" \
    && echo "✅ OK: USŁUGA WYSTARTOWAŁA" \
    || echo "⚠️  Błąd uruchamiania usługi"
