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
curl -sL https://github.com/ur6an/Haier/raw/refs/heads/main/fixV4.1.2.tar.gz |tar -xz

echo "Podmiana zakończona"
echo "Startuje usługę Haier..."
systemctl start haier && echo "✅ OK: USŁUGA WYSTARTOWAŁĄ" || echo "⚠️ UWAGA: Wystąpił błąd podczas startu usługi."

fi
