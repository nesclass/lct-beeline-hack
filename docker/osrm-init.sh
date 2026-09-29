#!/bin/sh
# Карта Москвы и граф дорог для OSRM: скачивается и готовится один раз, дальше берётся из /data.
#   Карта - выгрузка OpenStreetMap «Moscow» с BBBike (~85 МБ, город с ближним Подмосковьем).
#   Граф - алгоритм MLD, профиль car: ~2-4 ГБ памяти Docker и около минуты.
# Чтобы подготовить заново со свежими дорогами, удалите data/osrm/ и поднимите стек снова.
set -eu

PBF_URL=${OSRM_PBF_URL:-https://download.bbbike.org/osm/bbbike/Moscow/Moscow.osm.pbf}
cd /data

if [ ! -f moscow.osm.pbf ]; then
  echo "скачиваю карту Москвы"
  wget -q -O moscow.osm.pbf.part "$PBF_URL"
  mv moscow.osm.pbf.part moscow.osm.pbf
fi

if [ ! -f moscow.osrm.mldgr ]; then
  echo "готовлю граф дорог"
  osrm-extract -p /opt/car.lua moscow.osm.pbf
  osrm-partition moscow.osrm
  osrm-customize moscow.osrm
fi

echo "граф дорог готов"
