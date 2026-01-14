#!/bin/bash


# =============================================================
#            GŁÓWNA CZĘŚĆ SKRYPTU
# =============================================================

echo "Wklejam pliki z paczki alpha"

systemctl stop haier

rm -rf /opt/haier/static
rm -rf /opt/haier/templates
rm /opt/haier/main.py
cd /opt/haier
curl -sL https://github.com/ur6an/Haier/raw/refs/heads/main/fixV4.1.8.tar.gz |tar -xzv
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
echo "Startuje usługę Haier..."
systemctl start haier && echo "✅ OK: USŁUGA WYSTARTOWAŁA" || echo "⚠️ UWAGA: Wystąpił błąd podczas startu usługi."
