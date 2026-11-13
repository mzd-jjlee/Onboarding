#!/bin/sh
set -eu
# SeaTunnel 이미지 안에서만 실행. Java 클래스는 임시 디렉터리에 컴파일한다. 인자: check | create
CP='/opt/seatunnel/connectors/connector-iceberg-2.3.13.jar:/opt/seatunnel/lib/*:/opt/seatunnel/starter/seatunnel-starter.jar'
mkdir -p /tmp/catalog-classes
javac -cp "$CP" -d /tmp/catalog-classes /lab/scripts/PrepareRetailS3Catalog.java
java -Xmx512m -cp "/tmp/catalog-classes:$CP" PrepareRetailS3Catalog "$@"
