# Kurulum Kılavuzu

## Gereksinimler

- **Docker** ≥ 24.0
- **Docker Compose** v2 (`docker compose` komutu)
- Linux sunucu (Ubuntu 22.04 / Debian 12 önerilir)
- Açık portlar: `27015/tcp+udp` (CS2), `5000/tcp` (panel)

## 1. Depoyu klonlayın

```bash
git clone https://github.com/enesbakis/OpenCS2.git
cd OpenCS2
```

## 2. Ortam dosyasını oluşturun

```bash
cp .env.example .env
nano .env
```

En azından şu üç değeri ayarlayın:

```env
SECRET_KEY=<python3 -c "import secrets; print(secrets.token_hex(32))" ile üretin>
RCON_PASSWORD=güvenli_rcon_şifreniz
SERVER_IP=SUNUCU_PUBLIC_IP
```

## 3. Servisleri başlatın

```bash
docker compose up -d
```

CS2 sunucusunun yüklenmesi ~60 saniye sürer. Ardından paneli açın:

```
http://SUNUCU_IP:5000
```

Varsayılan giriş: **admin / changeme** — hemen değiştirin.

## 4. Sağlık kontrolü

```bash
docker compose ps
curl http://localhost:5000/health
# {"status": "ok"}
```

## Güncelleme

```bash
git pull
docker compose build panel
docker compose up -d panel
```

## Kaldırma

```bash
docker compose down -v   # konteynerler ve volume'lar silinir
```

> **Uyarı**: `-v` bayrağı panel veritabanını ve CS2 verilerini siler. Önce yedek alın.
