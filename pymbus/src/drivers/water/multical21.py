# src/drivers/water/multical21.py
"""
Kamstrup Multical 21 sayaç sürücüsü

Multical 21 C1 modu içindir. Bu sürücü, Kamstrup Multical 21 su sayaçlarından
gelen verileri çözümlemek için kullanılır.
"""

import logging
import struct
import datetime
from typing import Dict, Optional, Any, List

# Mutlak import
from pymbus.src.telegram import Telegram
from pymbus.src.protocol import MBusProtocol, MBusDataRecord, DeviceType
from pymbus.src.drivers.driver_base import DriverBase

logger = logging.getLogger(__name__)
class Multical21Driver(DriverBase):
    """Kamstrup Multical 21 su sayacı sürücüsü"""
    
    def __init__(self):
        """Sürücü başlatma"""
        super().__init__()
        self.name = "multical21"
        self.description = "Kamstrup Multical 21 water meter"
        self.manufacturer_codes = ["KAM"]  # Kamstrup
        self.meter_types = [DeviceType.WATER, DeviceType.COLD_WATER]
    
    def _parse_telegram_data(self, telegram: Telegram, 
                           data_records: List[MBusDataRecord]) -> Optional[Dict[str, Any]]:
        """
        Telegram veri alanını ayrıştırır
        
        Args:
            telegram: Telegram nesnesi
            data_records: Ayrıştırılmış veri kayıtları
            
        Returns:
            Optional[Dict[str, Any]]: Ayrıştırılmış veri veya None
        """
        result = {
            "media": "water",
            "meter": "multical21"
        }
        
        try:
            # Multical 21'e özgü veri yapısını ayrıştır
            # Gerçek uygulamada daha ayrıntılı bir ayrıştırma olacaktır
            
            for record in data_records:
                # Toplam hacim
                if record.get_description() == "Volume" and record.get_unit() == "m3":
                    result["total_m3"] = record.parsed_value
                
                # Akış hızı
                elif record.get_description() == "Volume Flow" and record.get_unit() == "m3/h":
                    result["flow_m3h"] = record.parsed_value
                
                # Akış sıcaklığı
                elif record.get_description() == "Flow Temperature" and record.get_unit() == "°C":
                    result["flow_temperature_c"] = record.parsed_value
                
                # Dış sıcaklık
                elif record.get_description() == "External Temperature" and record.get_unit() == "°C":
                    result["external_temperature_c"] = record.parsed_value
            
            # Durum bilgisi (Multical 21'e özgü)
            status_info = self._parse_status_bits(telegram.raw_data)
            if status_info:
                result.update(status_info)
            
            return result
            
        except Exception as e:
            logger.error(f"Veri ayrıştırma hatası: {e}", exc_info=True)
            return None
    
    def _parse_status_bits(self, data: bytes) -> Dict[str, Any]:
        """
        Multical 21 durum bitlerini ayrıştırır
        
        Args:
            data: Telegram verisi
            
        Returns:
            Dict[str, Any]: Durum bilgileri
        """
        status = {}
        
        # Bu, Multical 21'e özgü durum biti ayrıştırması için sadece bir örnek
        # Gerçek uygulamada sayacın tam bit yapısı bilinmelidir
        try:
            # Durum bitlerini al (bu örnek bir yaklaşımdır)
            # Gerçek bit konumları belgeye göre uyarlanmalıdır
            if len(data) >= 15:
                status_byte = data[14]
                
                # Durum bitlerini kontrol et
                if status_byte & 0x01:
                    status["leak_detected"] = True
                
                if status_byte & 0x02:
                    status["burst_detected"] = True
                
                if status_byte & 0x04:
                    status["dry_detected"] = True
                
                if status_byte & 0x08:
                    status["reverse_flow"] = True
                
                # Genel durum mesajı
                status_text = []
                if "leak_detected" in status:
                    status_text.append("LEAK")
                if "burst_detected" in status:
                    status_text.append("BURST")
                if "dry_detected" in status:
                    status_text.append("DRY")
                if "reverse_flow" in status:
                    status_text.append("REVERSE")
                
                if status_text:
                    status["status"] = " ".join(status_text)
                else:
                    status["status"] = "OK"
            
            return status
            
        except Exception as e:
            logger.error(f"Durum biti ayrıştırma hatası: {e}")
            return {}


# src/drivers/auto.py
"""
Otomatik sürücü tespiti
"""

import logging
import importlib
import pkgutil
from typing import Dict, Optional, Any, List

from pymbus.src.telegram import Telegram
from pymbus.src.protocol import MBusProtocol, MBusDataRecord, DeviceType
from pymbus.src.drivers.driver_base import DriverBase  # Burayı değiştirin

logger = logging.getLogger(__name__)

class AutoDriver:
    """Otomatik sürücü tespiti"""
    
    def __init__(self):
        """Sürücü başlatma"""
        self.drivers = []
        self._load_all_drivers()
    
    def _load_all_drivers(self) -> None:
        """Tüm sürücüleri yükler"""
        # Drivers paketindeki tüm kategorileri tara
        import pymbus.src.drivers as drivers_pkg
        
        for _, name, is_pkg in pkgutil.iter_modules(drivers_pkg.__path__):
            # Kategori mi?
            if is_pkg:
                # Kategori modülünü içe aktar
                category_pkg = importlib.import_module(f".{name}", "pymbus.src.drivers")
                
                # Kategorideki tüm modülleri tara
                for _, driver_name, _ in pkgutil.iter_modules(category_pkg.__path__):
                    # Sürücüyü yükle
                    try:
                        driver_module = importlib.import_module(
                            f".{name}.{driver_name}", "pymbus.src.drivers")
                        
                        # Sınıf adını tahmin et (ör. multical21 -> Multical21Driver)
                        class_name = f"{driver_name.capitalize()}Driver"
                        
                        if hasattr(driver_module, class_name):
                            driver_class = getattr(driver_module, class_name)
                            driver = driver_class()
                            self.drivers.append(driver)
                            logger.debug(f"Sürücü yüklendi: {driver_name}")
                    except Exception as e:
                        logger.error(f"Sürücü yükleme hatası: {driver_name} - {e}")
        
        logger.info(f"Toplam {len(self.drivers)} sürücü yüklendi")
    
    def find_driver(self, telegram: Telegram) -> Optional[str]:
        """
        Telegram için en uygun sürücüyü bulur
        
        Args:
            telegram: Telegram nesnesi
            
        Returns:
            Optional[str]: Sürücü adı veya None
        """
        if not telegram or not telegram.header:
            return None
        
        # Tüm sürücüleri dene
        for driver in self.drivers:
            if driver.can_handle(telegram):
                return driver.name
        
        return None
    
    def process_telegram(self, telegram: Telegram) -> Optional[Dict[str, Any]]:
        """
        Telegram'ı en uygun sürücü ile işler
        
        Args:
            telegram: Telegram nesnesi
            
        Returns:
            Optional[Dict[str, Any]]: İşlenmiş veri veya None
        """
        if not telegram or not telegram.header:
            return None
        
        # Tüm sürücüleri dene
        for driver in self.drivers:
            if driver.can_handle(telegram):
                result = driver.process_telegram(telegram)
                if result:
                    return result
        
        logger.warning(f"Uygun sürücü bulunamadı: {telegram.header.manufacturer}, "
                      f"type=0x{telegram.header.meter_type:02x}, "
                      f"ver=0x{telegram.header.version:02x}")
        return None


# src/utils/encryption.py
"""
Şifreleme ve şifre çözme yardımcıları
"""

import logging
import binascii
from typing import Union

logger = logging.getLogger(__name__)

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    CRYPTO_AVAILABLE = True
except ImportError:
    logger.warning("PyCryptodome kütüphanesi bulunamadı. Şifreleme desteği devre dışı.")
    CRYPTO_AVAILABLE = False

def decrypt_aes_cbc(data: bytes, key: str, manufacturer: str, meter_id: str) -> bytes:
    """
    AES-CBC şifreleme ile şifrelenmiş veriyi çözer
    
    Args:
        data: Şifreli veri
        key: Şifreleme anahtarı (hex string)
        manufacturer: Üretici kodu
        meter_id: Sayaç kimliği
        
    Returns:
        bytes: Çözülmüş veri
        
    Raises:
        ValueError: Şifreleme hatası
    """
    if not CRYPTO_AVAILABLE:
        raise ValueError("PyCryptodome kütüphanesi bulunamadı. Şifreleme desteği devre dışı.")
    
    if not key:
        raise ValueError("Şifre çözme için anahtar gerekli")
    
    try:
        # Hex anahtarını ikili veriye dönüştür
        key_bytes = binascii.unhexlify(key.replace(" ", ""))
        
        if len(key_bytes) != 16:
            raise ValueError(f"Geçersiz anahtar uzunluğu: {len(key_bytes)}, 16 byte olmalı")
        
        # IV oluştur (OMS standardına göre)
        # Bu örnek bir yaklaşımdır, gerçek uygulama değişebilir
        # Gerçek IV oluşturma şeması cihaza özgü olabilir
        iv = bytearray(16)
        
        # IV'ye üretici kodunu ekle
        for i, c in enumerate(manufacturer[:4]):
            if i < 16:
                iv[i] = ord(c)
        
        # IV'ye sayaç kimliğini ekle
        id_bytes = binascii.unhexlify(meter_id)
        for i, b in enumerate(id_bytes[:8]):
            if i + 4 < 16:
                iv[i + 4] = b
        
        # AES-CBC şifre çözme
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(data), AES.block_size)
        
        return decrypted
        
    except Exception as e:
        logger.error(f"Şifre çözme hatası: {e}")
        raise ValueError(f"Şifre çözme hatası: {e}") from e


# src/utils/logger.py
"""
Loglama yardımcıları
"""

import logging
import sys
import os
from typing import Optional

def setup_logger(
    name: str = "pymbus",
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    console: bool = True
) -> logging.Logger:
    """
    Logger ayarlarını yapılandırır
    
    Args:
        name: Logger adı
        level: Log seviyesi
        log_file: Log dosyası (isteğe bağlı)
        console: Konsola log yapılsın mı?
        
    Returns:
        logging.Logger: Yapılandırılmış logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Konsol handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # Dosya handler
    if log_file:
        # Dizin yoksa oluştur
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger