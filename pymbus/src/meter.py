"""
Sayaç modelleri ve taban sınıfı

Bu modül, sayaç modellerini ve taban sınıfını tanımlar. Telegram işleme
ve veri çıkarma işlemleri için kullanılır.
"""
import logging
import json
import datetime
from typing import Dict, List, Optional, Union, Any
import importlib

from .telegram import Telegram
from .protocol import DeviceType, LinkMode

logger = logging.getLogger(__name__)

class Meter:
    """Tüm sayaç tipleri için temel sınıf"""
    
    def __init__(self, name: str, meter_id: str, driver_name: str, key: Optional[str] = None):
        """
        Args:
            name: Sayaç için kullanıcı tanımlı isim
            meter_id: Sayaç kimliği (8 basamaklı hex)
            driver_name: Kullanılacak sürücü adı
            key: Şifreleme anahtarı (hex string, isteğe bağlı)
        """
        self.name = name
        self.id = meter_id
        self.driver_name = driver_name
        self.key = key
        self.driver = None
        self.last_reading = None
        self.last_telegram = None
        self.last_update = None
        
        # Link mode ayarlarını ayrıştır (örn. multical21:C1)
        parts = driver_name.split(':')
        self.driver_name = parts[0]
        self.link_mode = LinkMode.C1  # Varsayılan
        
        if len(parts) > 1:
            try:
                self.link_mode = LinkMode(parts[1].upper())
            except ValueError:
                logger.warning(f"Geçersiz link modu: {parts[1]}, varsayılan C1 kullanılıyor")
        
        self._load_driver()
    
    def _load_driver(self) -> None:
        """Sayaç için uygun sürücüyü yükler"""
        try:
            # Sürücü adına göre modülü dinamik olarak yükle
            if self.driver_name.lower() == 'auto':
                # "auto" özel durum, otomatik sürücü seçimi için
                from .drivers.auto import AutoDriver
                self.driver = AutoDriver()
            else:
                # Kategori ve sürücü adını belirle
                module_path = self._find_driver_module(self.driver_name)
                
                if not module_path:
                    logger.error(f"Sürücü bulunamadı: {self.driver_name}")
                    return
                    
                # Modülü yükle ve sürücü sınıfını oluştur
                module = importlib.import_module(module_path)
                driver_class = getattr(module, f"{self.driver_name.capitalize()}Driver")
                self.driver = driver_class()
                
            logger.info(f"Sürücü yüklendi: {self.driver_name}")
            
        except (ImportError, AttributeError) as e:
            logger.error(f"Sürücü yükleme hatası: {e}")
    
    def _find_driver_module(self, driver_name: str) -> Optional[str]:
        """
        Sürücü adına göre modül yolunu belirler
        
        Args:
            driver_name: Sürücü adı
            
        Returns:
            Optional[str]: Modül yolu veya None
        """
        # Desteklenen kategoriler
        categories = ['water', 'heat', 'electricity', 'gas']
        
        # Önce tüm kategorilerde ara
        for category in categories:
            try:
                module_path = f".drivers.{category}.{driver_name}"
                importlib.import_module(module_path, package="pymbus.src")
                return module_path
            except ImportError:
                continue
                
        # Kök drivers dizininde ara
        try:
            module_path = f".drivers.{driver_name}"
            importlib.import_module(module_path, package="pymbus.src")
            return module_path
        except ImportError:
            return None
    
    def process_telegram(self, telegram_data: Union[str, bytes]) -> bool:
        """
        Bir telegramı işler ve sayaç değerlerini günceller
        
        Args:
            telegram_data: İşlenecek telegram verisi
            
        Returns:
            bool: İşleme başarılı mı?
        """
        if not self.driver:
            logger.error(f"Sayaç sürücüsü yüklenmemiş: {self.name}")
            return False
            
        # Telegram nesnesini oluştur
        telegram = Telegram(telegram_data)
        
        # Telegram başlığı geçerli mi?
        if not telegram.header:
            logger.error("Geçersiz telegram başlığı")
            return False
            
        # Sayaç ID kontrolü
        if telegram.header.meter_id.lower() != self.id.lower():
            # Bu sayaca ait bir telegram değil
            return False
            
        # Şifreli ise, çöz
        if telegram.header.is_encrypted and not telegram.decrypt(self.key):
            logger.error(f"Telegram şifre çözme hatası: {self.name} ({self.id})")
            return False
            
        # Sürücüye veriyi işlet
        result = self.driver.process_telegram(telegram)
        
        if result:
            self.last_reading = result
            self.last_telegram = telegram
            self.last_update = datetime.datetime.now(datetime.timezone.utc)
            logger.info(f"Sayaç güncellendi: {self.name} ({self.id})")
            return True
        else:
            logger.error(f"Telegram işleme hatası: {self.name} ({self.id})")
            return False
    
    def get_reading(self) -> Dict[str, Any]:
        """
        Son okuma verilerini döndürür
        
        Returns:
            Dict[str, Any]: Sayaç okuma verileri sözlüğü
        """
        if not self.last_reading:
            return {}
            
        # Temel bilgileri ekle
        result = {
            "name": self.name,
            "id": self.id,
            "driver": self.driver_name,
            "timestamp": self.last_update.isoformat() if self.last_update else None
        }
        
        # Sürücü tarafından sağlanan verileri ekle
        result.update(self.last_reading)
        
        return result
    
    def to_json(self) -> str:
        """
        Son okumayı JSON formatında döndürür
        
        Returns:
            str: JSON formatında okuma verisi
        """
        reading = self.get_reading()
        if not reading:
            return "{}"
            
        return json.dumps(reading)
    
    def to_csv(self, fields: Optional[List[str]] = None, separator: str = ";") -> str:
        """
        Son okumayı CSV formatında döndürür
        
        Args:
            fields: Dahil edilecek alanlar (belirtilmezse tümü)
            separator: Alan ayırıcı
            
        Returns:
            str: CSV formatında okuma verisi
        """
        reading = self.get_reading()
        if not reading:
            return ""
            
        # Alan listesi belirtilmemişse tüm anahtarları kullan
        if not fields:
            fields = list(reading.keys())
            
        # Belirtilen alanlara göre değerleri birleştir
        values = [str(reading.get(field, "")) for field in fields]
        return separator.join(values)
    
    def to_human_readable(self) -> str:
        """
        Son okumayı insan okunabilir formatta döndürür
        
        Returns:
            str: İnsan okunabilir formatta okuma verisi
        """
        if not self.last_reading or not self.driver:
            return f"{self.name} ({self.id}): No reading"
            
        # Sürücünün kendi formatlama metodunu kullan (varsa)
        if hasattr(self.driver, "format_human_readable"):
            return self.driver.format_human_readable(self.name, self.id, self.last_reading)
            
        # Varsayılan insan okunabilir format
        reading = self.get_reading()
        parts = [f"{self.name} ({self.id})"]
        
        # Önemli değerleri ekle
        for key in sorted(reading.keys()):
            if key not in ['name', 'id', 'driver', 'manufacturer', 'timestamp']:
                value = reading[key]
                parts.append(f"{key}={value}")
        
        # Zaman damgası
        if 'timestamp' in reading:
            parts.append(f"at {reading['timestamp']}")
        
        return ' '.join(parts)

class WaterMeter(Meter):
    """Su sayacı sınıfı"""
    
    def __init__(self, name: str, meter_id: str, driver_name: str, key: Optional[str] = None):
        """
        Args:
            name: Sayaç için kullanıcı tanımlı isim
            meter_id: Sayaç kimliği (8 basamaklı hex)
            driver_name: Kullanılacak sürücü adı
            key: Şifreleme anahtarı (hex string, isteğe bağlı)
        """
        super().__init__(name, meter_id, driver_name, key)
        
        # Su sayaçları için özel özellikler 
        self.meter_type = "water"
        self.media_type = DeviceType.WATER
    
    def get_reading(self) -> Dict[str, Any]:
        """
        Son okuma verilerini döndürür
        
        Returns:
            Dict[str, Any]: Sayaç okuma verileri sözlüğü
        """
        result = super().get_reading()
        
        # Su sayaçları için özel alanlar
        result["media"] = "water"
        result["meter_type"] = self.meter_type
        
        return result

class HeatMeter(Meter):
    """Isı sayacı sınıfı"""
    
    def __init__(self, name: str, meter_id: str, driver_name: str, key: Optional[str] = None):
        """
        Args:
            name: Sayaç için kullanıcı tanımlı isim
            meter_id: Sayaç kimliği (8 basamaklı hex)
            driver_name: Kullanılacak sürücü adı
            key: Şifreleme anahtarı (hex string, isteğe bağlı)
        """
        super().__init__(name, meter_id, driver_name, key)
        
        # Isı sayaçları için özel özellikler
        self.meter_type = "heat"
        self.media_type = DeviceType.HEAT
    
    def get_reading(self) -> Dict[str, Any]:
        """
        Son okuma verilerini döndürür
        
        Returns:
            Dict[str, Any]: Sayaç okuma verileri sözlüğü
        """
        result = super().get_reading()
        
        # Isı sayaçları için özel alanlar
        result["media"] = "heat"
        result["meter_type"] = self.meter_type
        
        return result

class ElectricityMeter(Meter):
    """Elektrik sayacı sınıfı"""
    
    def __init__(self, name: str, meter_id: str, driver_name: str, key: Optional[str] = None):
        """
        Args:
            name: Sayaç için kullanıcı tanımlı isim
            meter_id: Sayaç kimliği (8 basamaklı hex)
            driver_name: Kullanılacak sürücü adı
            key: Şifreleme anahtarı (hex string, isteğe bağlı)
        """
        super().__init__(name, meter_id, driver_name, key)
        
        # Elektrik sayaçları için özel özellikler
        self.meter_type = "electricity"
        self.media_type = DeviceType.ELECTRICITY
    
    def get_reading(self) -> Dict[str, Any]:
        """
        Son okuma verilerini döndürür
        
        Returns:
            Dict[str, Any]: Sayaç okuma verileri sözlüğü
        """
        result = super().get_reading()
        
        # Elektrik sayaçları için özel alanlar
        result["media"] = "electricity"
        result["meter_type"] = self.meter_type
        
        return result

class GasMeter(Meter):
    """Gaz sayacı sınıfı"""
    
    def __init__(self, name: str, meter_id: str, driver_name: str, key: Optional[str] = None):
        """
        Args:
            name: Sayaç için kullanıcı tanımlı isim
            meter_id: Sayaç kimliği (8 basamaklı hex)
            driver_name: Kullanılacak sürücü adı
            key: Şifreleme anahtarı (hex string, isteğe bağlı)
        """
        super().__init__(name, meter_id, driver_name, key)
        
        # Gaz sayaçları için özel özellikler
        self.meter_type = "gas"
        self.media_type = DeviceType.GAS
    
    def get_reading(self) -> Dict[str, Any]:
        """
        Son okuma verilerini döndürür
        
        Returns:
            Dict[str, Any]: Sayaç okuma verileri sözlüğü
        """
        result = super().get_reading()
        
        # Gaz sayaçları için özel alanlar
        result["media"] = "gas"
        result["meter_type"] = self.meter_type
        
        return result

def create_meter(meter_type: str, name: str, meter_id: str, driver_name: str, key: Optional[str] = None) -> Meter:
    """
    Sayaç tipine göre sayaç nesnesi oluşturur
    
    Args:
        meter_type: Sayaç tipi ('water', 'heat', 'electricity', 'gas')
        name: Sayaç için kullanıcı tanımlı isim
        meter_id: Sayaç kimliği (8 basamaklı hex)
        driver_name: Kullanılacak sürücü adı
        key: Şifreleme anahtarı (hex string, isteğe bağlı)
        
    Returns:
        Meter: Sayaç nesnesi
        
    Raises:
        ValueError: Geçersiz sayaç tipi
    """
    # Sayaç tipine göre uygun sınıfı seç
    if meter_type.lower() == 'water':
        return WaterMeter(name, meter_id, driver_name, key)
    elif meter_type.lower() == 'heat':
        return HeatMeter(name, meter_id, driver_name, key)
    elif meter_type.lower() == 'electricity':
        return ElectricityMeter(name, meter_id, driver_name, key)
    elif meter_type.lower() == 'gas':
        return GasMeter(name, meter_id, driver_name, key)
    else:
        # Bilinmeyen sayaç tipi, genel sayaç oluştur
        logger.warning(f"Bilinmeyen sayaç tipi: {meter_type}, genel sayaç oluşturuluyor")
        return Meter(name, meter_id, driver_name, key)