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
curl -sL https://github.com/ur6an/Haier/raw/refs/heads/main/fixV4.1.4.tar.gz |tar -xzv
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
    exit 0
fi

# Pytanie do użytkownika
while true; do
    read -rp "Czy korzystasz z CWU? (tak/nie): " answer
    case "$answer" in
        [Tt][Aa][Kk]|[Tt]|[Yy]|[Yy][Ee][Ss])
            VALUE=1
            break
            ;;
        [Nn][Ii][Ee]|[Nn]|[Nn][Oo])
            VALUE=0
            break
            ;;
        *)
            echo "Proszę odpowiedzieć: tak lub nie"
            ;;
    esac
done

# Dodanie wpisu po [SETTINGS]
awk -v val="$VALUE" '
/^\[SETTINGS\]/ {
    print
    print "dhwuse = " val
    next
}
{ print }
' "$FILE" > "${FILE}.tmp" && mv "${FILE}.tmp" "$FILE"

echo "Startuje usługę Haier..."
systemctl start haier && echo "✅ OK: USŁUGA WYSTARTOWAŁĄ" || echo "⚠️ UWAGA: Wystąpił błąd podczas startu usługi."
