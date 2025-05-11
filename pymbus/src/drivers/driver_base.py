"""
Tüm sayaç sürücüleri için temel sınıf

Bu modül, tüm sayaç sürücülerinin miras alması gereken temel sınıfı tanımlar.
Sürücü geliştirmek için bu sınıftan türetilmelidir.
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any, Tuple, List

from ..telegram import Telegram
from ..protocol import DeviceType, MBusProtocol, MBusDataRecord

logger = logging.getLogger(__name__)

class DriverBase(ABC):
    """Sayaç sürücüleri için soyut temel sınıf"""
    
    def __init__(self):
        """Sürücü başlatma"""
        self.name = "base"
        self.description = "Base driver"
        self.manufacturer_codes = []  # Desteklenen üretici kodları
        self.meter_types = []  # Desteklenen sayaç tipleri
        self.meter_versions = []  # Desteklenen sayaç versiyonları
    
    def can_handle(self, telegram: Telegram) -> bool:
        """
        Bu sürücünün telegram'ı işleyip işleyemeyeceğini kontrol eder
        
        Args:
            telegram: Telegram nesnesi
            
        Returns:
            bool: Bu sürücü telegramı işleyebilir mi?
        """
        if not telegram or not telegram.header:
            return False
            
        # Üretici kontrolü
        if self.manufacturer_codes and telegram.header.manufacturer not in self.manufacturer_codes:
            return False
            
        # Sayaç tipi kontrolü
        if self.meter_types and telegram.header.meter_type not in self.meter_types:
            return False
            
        # Versiyon kontrolü
        if self.meter_versions and telegram.header.version not in self.meter_versions:
            return False
            
        return True
    
    def process_telegram(self, telegram: Telegram) -> Optional[Dict[str, Any]]:
        """
        Telegramı işleyerek sayaç verilerini çıkarır
        
        Args:
            telegram: İşlenecek telegram nesnesi
            
        Returns:
            Optional[Dict[str, Any]]: Çıkarılan sayaç değerleri veya None
        """
        if not self.can_handle(telegram):
            return None
            
        try:
            # Veri alanını çözümle - sürücü özelleştirmesi gereken kısım
            data_records = MBusProtocol.parse_data_records(telegram.raw_data[10:])
            
            # Temel bilgileri içeren sözlüğü oluştur
            result = {
                "manufacturer": telegram.header.manufacturer,
                "meter_type": self._get_meter_type_name(telegram.header.meter_type),
                "meter_version": f"0x{telegram.header.version:02x}"
            }
            
            # Sürücü özel veri ayrıştırma - alt sınıflar tarafından uygulanır
            parsed_data = self._parse_telegram_data(telegram, data_records)
            
            if parsed_data:
                result.update(parsed_data)
                
            return result
            
        except Exception as e:
            logger.error(f"Telegram işleme hatası: {e}", exc_info=True)
            return None
    
    @abstractmethod
    def _parse_telegram_data(self, telegram: Telegram, 
                           data_records: List[MBusDataRecord]) -> Optional[Dict[str, Any]]:
        """
        Telegram veri alanını ayrıştırır - alt sınıflar tarafından uygulanır
        
        Args:
            telegram: Telegram nesnesi
            data_records: Ayrıştırılmış veri kayıtları
            
        Returns:
            Optional[Dict[str, Any]]: Ayrıştırılmış veri veya None
        """
        pass
    
    def _get_meter_type_name(self, type_code: int) -> str:
        """
        Sayaç tipi koduna göre açıklama döndürür
        
        Args:
            type_code: Sayaç tipi kodu
            
        Returns:
            str: Sayaç tipi açıklaması
        """
        try:
            return DeviceType(type_code).name.lower().replace('_', ' ')
        except ValueError:
            return f"unknown (0x{type_code:02x})"

    def get_fields(self) -> List[Dict[str, Any]]:
        """
        Bu sürücü tarafından desteklenen alanların listesini döndürür
        
        Returns:
            List[Dict[str, Any]]: Alan bilgileri listesi
        """
        # Alt sınıflar bu metodu geçersiz kılabilir
        # Varsayılan olarak temel alanlar döndürülür
        return [
            {
                "name": "manufacturer",
                "description": "Manufacturer code",
                "unit": None,
                "type": "string"
            },
            {
                "name": "meter_type",
                "description": "Meter type",
                "unit": None,
                "type": "string"
            },
            {
                "name": "meter_version",
                "description": "Meter firmware version",
                "unit": None,
                "type": "string"
            }
        ]
    
    def format_json(self, name: str, meter_id: str, reading: Dict[str, Any]) -> str:
        """
        Okuma verisini JSON formatında biçimlendirir (yardımcı metod)
        
        Args:
            name: Sayaç adı
            meter_id: Sayaç kimliği
            reading: Okuma verileri sözlüğü
            
        Returns:
            str: JSON formatında veri
        """
        import json
        
        # Temel bilgileri ekle
        result = {
            "name": name,
            "id": meter_id,
            "driver": self.name,
        }
        
        # Okuma verilerini ekle
        result.update(reading)
        
        # JSON'a dönüştür
        return json.dumps(result)
        
    def format_csv(self, name: str, meter_id: str, reading: Dict[str, Any], 
                  fields: Optional[List[str]] = None, separator: str = ";") -> str:
        """
        Okuma verisini CSV formatında biçimlendirir (yardımcı metod)
        
        Args:
            name: Sayaç adı
            meter_id: Sayaç kimliği
            reading: Okuma verileri sözlüğü
            fields: Dahil edilecek alanlar (belirtilmezse tümü)
            separator: Alan ayırıcı
            
        Returns:
            str: CSV formatında veri
        """
        # Temel bilgileri ekle
        result = {
            "name": name,
            "id": meter_id,
            "driver": self.name,
        }
        
        # Okuma verilerini ekle
        result.update(reading)
        
        # Alan listesi belirtilmemişse tüm anahtarları kullan
        if not fields:
            fields = list(result.keys())
            
        # Belirtilen alanlara göre değerleri birleştir
        values = [str(result.get(field, "")) for field in fields]
        return separator.join(values)

    def format_human_readable(self, name: str, meter_id: str, reading: Dict[str, Any]) -> str:
        """
        Okuma verisini insan okunabilir formatta biçimlendirir (yardımcı metod)
        
        Args:
            name: Sayaç adı
            meter_id: Sayaç kimliği
            reading: Okuma verileri sözlüğü
            
        Returns:
            str: İnsan okunabilir formatta veri
        """
        # Basit bir insan okunabilir format
        parts = [name, meter_id]
        
        # Önemli değerleri ekle
        for key in sorted(reading.keys()):
            if key not in ['manufacturer', 'meter_type', 'meter_version']:
                value = reading[key]
                parts.append(f"{value}")
        
        # Zaman damgası
        if 'timestamp' in reading:
            parts.append(reading['timestamp'])
        
        return ' '.join(map(str, parts))