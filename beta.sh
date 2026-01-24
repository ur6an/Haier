#!/bin/bash


# =============================================================
#            GŁÓWNA CZĘŚĆ SKRYPTU
# =============================================================

echo "Wklejam pliki z paczki beta"

systemctl stop haier

rm -rf /opt/haier/static
rm -rf /opt/haier/templates
rm /opt/haier/main.py
cd /opt/haier
curl -sL https://github.com/ur6an/Haier/raw/refs/heads/main/fixV4.1.9.tar.gz |tar -xz
cp /opt/config.ini /opt/config.ini.backup

echo "Podmiana zakończona"

#Dodawanie wpisu dhw
FILE="/opt/config.ini"

if [[ ! -f "$FILE" ]]; then
    echo "Plik $FILE nie istnieje"
    exit 1
fi

# Sprawdzenie czy wpis już istnieje
if grep -Eq '^[[:space:]]*dhwuse[[:space:]]*=[[:space:]]*[01]' "$FILE"; then
    ZAKONCZ=1
    echo "Wpis cwu istnieje"
fi

if (( ZAKONCZ != 1 )); then
echo "Wpis cwu nie istnieje"
# Pytanie do użytkownika

echo
read -p "Czy korzystasz z CWU? [t/n]: " -n 1 -r answer < /dev/tty
echo

if [[ "$answer" =~ ^[Tt]$ ]]; then
    VALUE=1
else
    VALUE=0
fi

# Dodanie wpisu po [SETTINGS]
awk -v val="$VALUE" '
/^\[SETTINGS\]/ {
    print
    print "dhwuse = " val
    next
}
{ print }
' "$FILE" > "${FILE}.tmp" && mv "${FILE}.tmp" "$FILE"
fi
ZAKONCZ=0
# Sprawdzenie czy wpis zone już istnieje
if grep -Eq '^[[:space:]]*zone_frost_enable[[:space:]]*=[[:space:]]*[01]' "$FILE"; then
    ZAKONCZ=1
    echo "Wpis zone istnieje"
fi

if (( ZAKONCZ != 1 )); then
echo "Wpis zone nie istnieje"
# Dodanie wpisu po [SETTINGS]
awk -v val="$VALUE" '
/^\[SETTINGS\]/ {
    print
    print "zone_frost_enable = 0"
    print "zone_frost_temp = -5"
    print "zone_frost_mode = quiet"
    print "zone_warm_enable = 0"
    print "zone_warm_temp = 10"
    print "zone_warm_mode = quiet_flimit"
    next
}
{ print }
' "$FILE" > "${FILE}.tmp" && mv "${FILE}.tmp" "$FILE"
fi
echo "Startuje usługę Haier..."
systemctl start haier && echo "✅ OK: USŁUGA WYSTARTOWAŁA" || echo "⚠️ UWAGA: Wystąpił błąd podczas startu usługi."
