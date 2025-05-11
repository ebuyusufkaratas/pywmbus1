# test_telegram.py
import os
import sys
import logging

# Pymbus modülünü import et
# Paket yolu ayarı (gerekirse)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import gerekli sınıflar
from pymbus.src.telegram import Telegram
from pymbus.src.protocol import MBusProtocol
from pymbus.src.drivers.auto import AutoDriver

# Logging ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_telegram")

# Test edilecek hex string
telegram_hex = "374493444836351218067ac70000200c13911900004c1391170000426cbf2ccc081391170000c2086cbf2c02bb560000326cffff046d1e02de21fed0"

def test_telegram():
    # Telegram nesnesini oluştur
    telegram = Telegram(telegram_hex)
    
    
    # Telegram bilgilerini yazdır
    if telegram.header:
        logger.info(f"Telegram üreticisi: {telegram.header.manufacturer}")
        logger.info(f"Sayaç ID: {telegram.header.meter_id}")
        logger.info(f"Sayaç tipi: 0x{telegram.header.meter_type:02x}")
        logger.info(f"Sayaç versiyonu: 0x{telegram.header.version:02x}")
        logger.info(f"Şifreli: {telegram.header.is_encrypted}")
    else:
        logger.error("Telegram başlığı ayrıştırılamadı!")
        return
    
    # Telegram verisini ayrıştır
    parsed_data = telegram.parse_data()
    logger.info(f"Ayrıştırılmış veri: {parsed_data}")
    
    # Otomatik sürücü ile analiz et
    auto_driver = AutoDriver()
    result = auto_driver.process_telegram(telegram)
    
    if result:
        logger.info("Sürücü analiz sonucu:")
        for key, value in result.items():
            logger.info(f"  {key}: {value}")
    else:
        logger.info("Uygun sürücü bulunamadı veya ayrıştırma başarısız")

    # Veri kayıtlarını ayrıştır
    try:
        # Telegram veri alanını ayrıştır
        data_records = MBusProtocol.parse_data_records(telegram.raw_data[10:])
        logger.info(f"{len(data_records)} veri kaydı bulundu:")
        
        for i, record in enumerate(data_records):
            logger.info(f"  Kayıt #{i+1}: {record.get_description()} = {record.parsed_value} {record.get_unit()}")
    except Exception as e:
        logger.error(f"Veri kayıtları ayrıştırılırken hata: {e}")

if __name__ == "__main__":
    test_telegram()