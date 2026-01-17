#!/bin/bash

# =============================================================
#            KONFIGURACJA
# =============================================================
PARTYCJA="/opt"
WYMAGANE_WOLNE_MIEJSCE_MB=100
KATALOG_DO_PRZESZUKANIA_ETAP1="/opt"
WYKLUCZENIE_ETAP1="/opt/haier"
KATALOG_DO_PRZESZUKANIA_ETAP2="/opt/haier/env"
RPI='arm32v6'
NEO='arm32v7'

# =============================================================
#            FUNKCJA PROPONUJĄCA PLIKI DO USUNIĘCIA
# =============================================================
rm -rf /opt/haier.backup 
rm -rf /opt/haier/env 
rm /opt/HAIER* 
zaproponuj_usuniecie() {
  local LOKALNE_WOLNE_MIEJSCE_KB=$1
  local LOKALNY_PROG_KB=$2
  local ILE_BRAKUJE_KB=$(( LOKALNY_PROG_KB - LOKALNE_WOLNE_MIEJSCE_KB ))

  # Tablica na wszystkich kandydatów
  declare -a KANDYDACI_DO_USUNIECIA=()
  local LACZNY_ROZMIAR_KANDYDATOW=0

  echo "Brakuje co najmniej $ILE_BRAKUJE_KB KB wolnego miejsca. Rozpoczynam poszukiwania..."
  echo "---"

  # --- ETAP 1: Skanowanie głównego katalogu /opt ---
  echo "Etap 1: Skanowanie $KATALOG_DO_PRZESZUKANIA_ETAP1 (z wyłączeniem $WYKLUCZENIE_ETAP1)..."
  
  # Używamy pętli do wczytania wyników i sumowania rozmiaru
  while IFS= read -r linia; do
    if [[ -n "$linia" ]]; then
      KANDYDACI_DO_USUNIECIA+=("$linia")
      ROZMIAR=$(echo "$linia" | awk '{print $1}')
      LACZNY_ROZMIAR_KANDYDATOW=$(( LACZNY_ROZMIAR_KANDYDATOW + ROZMIAR ))
    fi
  done < <(find "$KATALOG_DO_PRZESZUKANIA_ETAP1" -mindepth 1 -maxdepth 1 \
            | grep -v "$WYKLUCZENIE_ETAP1" \
            | xargs -d '\n' du -sk 2>/dev/null \
            | sort -rn)

  # --- SPRAWDZENIE PO ETAPIE 1 ---
  if [[ "$LACZNY_ROZMIAR_KANDYDATOW" -lt "$ILE_BRAKUJE_KB" ]]; then
    echo "Niewystarczająca ilość miejsca po Etapie 1. (Znaleziono: $LACZNY_ROZMIAR_KANDYDATOW KB)"
    echo "---"
    # --- ETAP 2: Skanowanie katalogu /opt/haier/env ---
    echo "Etap 2: Skanowanie dodatkowego katalogu $KATALOG_DO_PRZESZUKANIA_ETAP2..."
    while IFS= read -r linia; do
      if [[ -n "$linia" ]]; then
        KANDYDACI_DO_USUNIECIA+=("$linia")
        ROZMIAR=$(echo "$linia" | awk '{print $1}')
        LACZNY_ROZMIAR_KANDYDATOW=$(( LACZNY_ROZMIAR_KANDYDATOW + ROZMIAR ))
      fi
    done < <(find "$KATALOG_DO_PRZESZUKANIA_ETAP2" -mindepth 1 -maxdepth 1 \
              | xargs -d '\n' du -sk 2>/dev/null \
              | sort -rn)
  fi

   # --- OSTATECZNE SPRAWDZENIE I PROPOZYCJA ---
  if [[ "$LACZNY_ROZMIAR_KANDYDATOW" -lt "$ILE_BRAKUJE_KB" ]]; then
    echo "❌ BŁĄD: Nawet po przeskanowaniu wszystkich lokalizacji, nie można zwolnić wymaganej ilości miejsca."
    echo "   (Można zwolnić maksymalnie: $LACZNY_ROZMIAR_KANDYDATOW KB z wymaganych $ILE_BRAKUJE_KB KB)"
    return 1 # Zakończ funkcję z kodem błędu
  fi

  echo "Znaleziono wystarczającą ilość kandydatów do usunięcia."
  echo "Proponowane operacje (od największych):"

  local ZWALNIANE_MIEJSCE_KB=0
  declare -a FINALNA_LISTA_DO_USUNIECIA=()

  # POPRAWIONA PĘTLA - UŻYCIE 'PROCESS SUBSTITUTION' (< <(...))
  # To sprawia, że pętla nie działa w subshellu i może modyfikować zmienne.
  while read -r ROZMIAR SCIEZKA; do
    if [[ "$ZWALNIANE_MIEJSCE_KB" -ge "$ILE_BRAKUJE_KB" ]]; then
      break
    fi

    echo "  - [ ROZMIAR: ${ROZMIAR} KB ] Ścieżka: $SCIEZKA"
    ZWALNIANE_MIEJSCE_KB=$(( ZWALNIANE_MIEJSCE_KB + ROZMIAR ))
    FINALNA_LISTA_DO_USUNIECIA+=("$SCIEZKA")
  done < <( (for kandydat in "${KANDYDACI_DO_USUNIECIA[@]}"; do echo "$kandydat"; done) | sort -rn )


  echo "---"
  echo "Usunięcie powyższych elementów zwolni łącznie ~${ZWALNIANE_MIEJSCE_KB} KB."
  echo ""

  # Ta część pozostaje bez zmian
  #read -p "Czy na pewno chcesz usunąć powyższe pliki i katalogi? [T/n]: " -n 1 -r ODPOWIEDZ
  read -p "Czy na pewno chcesz usunąć powyższe pliki i katalogi? [T/n]: " -n 1 -r ODPOWIEDZ < /dev/tty
  echo

  if [[ "$ODPOWIEDZ" =~ ^[Tt]$ ]]; then
    echo "Potwierdzono. Rozpoczynam usuwanie..."
    for plik in "${FINALNA_LISTA_DO_USUNIECIA[@]}"; do
      echo "Usuwam: $plik"
      # rm -rf "$plik" # UWAGA: Ta linia wykonuje faktyczne usuwanie
    done
    echo "✅ Zakończono usuwanie."
  else
    echo "Anulowano. Żadne pliki nie zostały usunięte."
  fi
}

# =============================================================
#            GŁÓWNA CZĘŚĆ SKRYPTU
# =============================================================

PROG_KB=$(( WYMAGANE_WOLNE_MIEJSCE_MB * 1024 ))

echo "Sprawdzam wolne miejsce na partycji $PARTYCJA..."
WOLNE_MIEJSCE_KB=$(df --output=avail "$PARTYCJA" | tail -n 1 | tr -d ' ')

if [[ "$WOLNE_MIEJSCE_KB" -gt "$PROG_KB" ]]; then
  echo "✅ OK: Jest więcej niż $WYMAGANE_WOLNE_MIEJSCE_MB MB wolnego miejsca."
else
  echo "⚠️ UWAGA: Jest za mało wolnego miejsca (dostępne: $WOLNE_MIEJSCE_KB KB, wymagane: $PROG_KB KB)."
  echo ""
  zaproponuj_usuniecie "$WOLNE_MIEJSCE_KB" "$PROG_KB"
fi

if grep -q "ARMv7" /proc/cpuinfo; then
  echo "✅ OK: Znalazłem SBC NanoPi NEO 1.4"
  ARCH=$NEO
elif grep -q "ARMv6" /proc/cpuinfo; then
  echo "✅ OK: Znalazłem SBC RaspberryPi zero W"
  ARCH=$RPI
else
        echo "⚠️ UWAGA: Nie znalazłem żadnej z wymaganych architektur (ARMv6 lub ARMv7)"
	exit 1
fi
echo
read -p "Czy rozpocząć instalację HaierPi? [T/n]: " -n 1 -r ODP < /dev/tty
echo

if [[ "$ODP" =~ ^[Tt]$ ]]; then


systemctl stop haier
cd /opt
#curl -s -OJ http://haierpi.pl:3000/api/packages/haierpi/generic/haierpi/v1.4beta12/HAIERPI--$ARCH.tar.gz
#curl -sL https://gitea.haierpi.pl/api/packages/haierpi/generic/haierpi/v1.4beta12/HAIERPI-v1.4beta12-arm32v6.tar.gz |tar -xz
cp /opt/haier/config.ini /opt
cp /opt/haier/users.json /opt
cp /opt/haier/schedule_ch.json /opt
cp /opt/haier/schedule_dhw.json /opt

mv /opt/haier /opt/haier.backup

#tar -xzf HAIERPI--$ARCH.tar.gz
curl -sL https://gitea.haierpi.pl/api/packages/haierpi/generic/haierpi/v1.4beta10/HAIERPI--$ARCH.tar.gz |tar -xz
mv /opt/users.json /opt/haier/
mv /opt/schedule_ch.json /opt/haier/
mv /opt/schedule_dhw.json /opt/haier/
cp /opt/haier.backup/charts.pkl /opt/haier/

echo "Wklejam pliki z paczki alpha"

systemctl stop haier

rm -rf /opt/haier/static
rm -rf /opt/haier/templates
rm /opt/haier/main.py
cd /opt/haier
curl -sL https://github.com/ur6an/Haier/raw/refs/heads/main/fixV4.1.8.tar.gz |tar -xz
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

echo "✅ OK: Instalacja zakończona"
echo "Startuje usługę Haier..."
systemctl start haier && echo "✅ OK: USŁUGA WYSTARTOWAŁA" || echo "⚠️ UWAGA: Wystąpił błąd podczas startu usługi."

fi

