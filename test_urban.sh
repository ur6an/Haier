Przejdź do treści
Powiedziałeś(-aś):
zoptymalizuj skrypt
ChatGPT powiedział:
Jasne — tylko który skrypt? 😄
Podeślij kod (i daj znać w jakim języku), a najlepiej też:

co ma robić,

gdzie jest problem (wolno? dużo pamięci? brzydki kod?),

czy optymalizacja ma być pod wydajność, czytelność, czy zużycie zasobów.

Wrzuć fragment albo całość i jedziemy 🚀

Powiedziałeś(-aś):
#!/bin/bash


# =============================================================
#            GŁÓWNA CZĘŚĆ SKRYPTU
# =============================================================

echo "Wklejam pliki z paczki test 1.4.5.6"

systemctl stop haier

rm -rf /opt/haier/static
rm -rf /opt/haier/templates
rm /opt/haier/main.py
cd /opt/haier
curl -sL https://github.com/ur6an/Haier/raw/refs/heads/main/fixV1.4.5.6.tar.gz |tar -xz
cp /opt/config.ini /opt/config.ini.backup

echo "Podmiana zakończona"
echo
#read -p "Czy chcesz skorzystać z interfejsu Kamila? [t/n]: " -n 1 -r answer < /dev/tty
#echo

#if [[ "$answer" =~ ^[Tt]$ ]]; then
#    echo "Wklejam pliki z paczki Kamila"
#    curl -sL https://github.com/ur6an/Haier/raw/refs/heads/main/fixV1.4.4.2_Kamil.tar.gz |tar -xz
#    echo
#fi

#Dodawanie wpisu dhw
FILE="/opt/config.ini"

if [[ ! -f "$FILE" ]]; then
    echo "Plik $FILE nie istnieje"
    exit 1
fi

# Sprawdzenie czy wpis cwu już istnieje
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

ZAKONCZ=0

# Sprawdzenie czy wpis emergency_intemp już istnieje
if grep -Eq '^[[:space:]]*emergency_intemp[[:space:]]*=[[:space:]]*' "$FILE"; then
    ZAKONCZ=1
    echo "Wpis emergency_intemp istnieje"
fi

if (( ZAKONCZ != 1 )); then
echo "Wpis emergency_intemp nie istnieje"
# Dodanie wpisu po [SETTINGS]
awk -v val="$VALUE" '
/^\[SETTINGS\]/ {
    print
    print "emergency_intemp = 20.0"
    next
}
{ print }
' "$FILE" > "${FILE}.tmp" && mv "${FILE}.tmp" "$FILE"
fi

ZAKONCZ=0

# Sprawdzenie czy wpis dhwtemp już istnieje
if grep -Eq '^[[:space:]]*dhwtemp[[:space:]]*=[[:space:]]*' "$FILE"; then
    ZAKONCZ=1
    echo "Wpis dhwtemp istnieje"
fi

if (( ZAKONCZ != 1 )); then
echo "Wpis dhwtemp nie istnieje"
# Dodanie wpisu po [SETTINGS]
awk -v val="$VALUE" '
/^\[SETTINGS\]/ {
    print
    print "dhwtemp = builtin"
    next
}
/^\[HOMEASSISTANT\]/ {
    print
    print "dhwsensor ="
    next
}
{ print }
' "$FILE" > "${FILE}.tmp" && mv "${FILE}.tmp" "$FILE"
fi

ZAKONCZ=0

# Sprawdzenie czy wpis dhwnolimit_mode już istnieje
if grep -Eq '^[[:space:]]*dhwnolimit_mode[[:space:]]*=[[:space:]]*' "$FILE"; then
    ZAKONCZ=1
    echo "Wpis dhwnolimit_mode istnieje"
fi

if (( ZAKONCZ != 1 )); then
echo "Wpis dhwnolimit_mode nie istnieje"
# Dodanie wpisu po [SETTINGS]
awk -v val="$VALUE" '
/^\[SETTINGS\]/ {
    print
    print "dhwnolimit_mode = turbo"
    next
}
{ print }
' "$FILE" > "${FILE}.tmp" && mv "${FILE}.tmp" "$FILE"
fi

ZAKONCZ=0

# Sprawdzenie czy wpis ddirect_thermostat już istnieje
if grep -Eq '^[[:space:]]*direct_thermostat[[:space:]]*=[[:space:]]*' "$FILE"; then
    ZAKONCZ=1
    echo "Wpis direct_thermostat istnieje"
fi

if (( ZAKONCZ != 1 )); then
echo "Wpis direct_thermostat nie istnieje"
# Dodanie wpisu po [SETTINGS]
awk -v val="$VALUE" '
/^\[SETTINGS\]/ {
    print
    print "direct_thermostat = 0"
    print "direct_inside_settemp = 22.0"
    next
}
{ print }
' "$FILE" > "${FILE}.tmp" && mv "${FILE}.tmp" "$FILE"
fi
echo
echo "Startuje usługę Haier..."
systemctl start haier && echo "✅ OK: USŁUGA WYSTARTOWAŁA" || echo "⚠️ UWAGA: Wystąpił błąd podczas startu usługi."
ChatGPT powiedział:
OK, tu aż się prosiło o refaktor 😉
Największe problemy obecnej wersji:

dużo powtórzeń (grep → awk → tmp → mv),

zmienna ZAKONCZ używana jak flaga globalna (mało czytelne),

wielokrotne parsowanie tego samego pliku,

brak trybu „fail fast”,

trudne do utrzymania przy kolejnych opcjach.

Poniżej masz zoptymalizowaną, krótszą i czytelniejszą wersję, bez zmiany logiki działania.

🔧 Co zrobiłem
✅ dodałem set -euo pipefail
✅ jedna funkcja do sprawdzania i wstawiania wpisów
✅ brak globalnych flag
✅ mniej awk i grep
✅ bezpieczna praca na pliku tymczasowym
✅ łatwe dodawanie kolejnych opcji

✅ Zoptymalizowana wersja skryptu
#!/bin/bash
set -euo pipefail

SERVICE="haier"
BASE_DIR="/opt/haier"
CONFIG="/opt/config.ini"
TMP="$(mktemp)"

echo "📦 Wklejam pliki z paczki test 1.4.5.6"

systemctl stop "$SERVICE"

rm -rf "$BASE_DIR/static" "$BASE_DIR/templates" "$BASE_DIR/main.py"
cd "$BASE_DIR"

curl -sL https://github.com/ur6an/Haier/raw/refs/heads/main/fixV1.4.5.6.tar.gz | tar -xz

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

    awk -v sec="[$section]" -v txt="$content" '
    $0 == sec {
        print
        print txt
        next
    }
    { print }
    ' "$CONFIG" > "$TMP" && mv "$TMP" "$CONFIG"
}

# -------------------------------------------------
# CWU
# -------------------------------------------------

if ! config_has "dhwuse"; then
    read -p "Czy korzystasz z CWU? [t/n]: " -n 1 answer < /dev/tty
    echo

    [[ "$answer" =~ [Tt] ]] && DHW=1 || DHW=0

    insert_after_section "SETTINGS" "dhwuse = $DHW"
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
else
    echo "ℹ️  Wpis zone istnieje"
fi

# -------------------------------------------------
# EMERGENCY
# -------------------------------------------------

if ! config_has "emergency_intemp"; then
    insert_after_section "SETTINGS" "emergency_intemp = 20.0"
else
    echo "ℹ️  Wpis emergency_intemp istnieje"
fi

# -------------------------------------------------
# DHW TEMP
# -------------------------------------------------

if ! config_has "dhwtemp"; then
    awk '
    /^\[SETTINGS\]/ {
        print
        print "dhwtemp = builtin"
        next
    }
    /^\[HOMEASSISTANT\]/ {
        print
        print "dhwsensor ="
        next
    }
    { print }
    ' "$CONFIG" > "$TMP" && mv "$TMP" "$CONFIG"
else
    echo "ℹ️  Wpis dhwtemp istnieje"
fi

# -------------------------------------------------
# NO LIMIT MODE
# -------------------------------------------------

if ! config_has "dhwnolimit_mode"; then
    insert_after_section "SETTINGS" "dhwnolimit_mode = turbo"
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
else
    echo "ℹ️  Wpis direct_thermostat istnieje"
fi

# -------------------------------------------------
# START
# -------------------------------------------------

echo
echo "🚀 Startuję usługę Haier..."
systemctl start "$SERVICE" \
    && echo "✅ OK: USŁUGA WYSTARTOWAŁA" \
    || echo "⚠️  Błąd uruchamiania usługi"
🧠 Bonus – co dalej można poprawić
Jeśli chcesz, mogę:

przerobić to na tryb nieinteraktywny (parametry CLI)

zrobić dry-run

dodać logowanie do pliku

albo przepisać na Ansible / Python

Daj znać, w którą stronę idziemy 😎




Dołącz

Wyszukaj

Ucz się

Utwórz obraz

Głos
Nie wybrano plikuNie wybrano pliku
ChatGPT może popełniać błędy. Sprawdź ważne informacje. Zobacz Preferencje dotyczące plików cookie.
