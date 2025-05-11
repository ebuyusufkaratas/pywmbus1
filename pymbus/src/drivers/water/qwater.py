"""
Qundis su sayaçları için sürücü

Bu modül, Qundis su sayaçları için telegram ayrıştırma ve
veri çözümleme desteği sağlar.

Desteklenen cihazlar:
- Q water 5.5 (QDC)
- Q water S (QWSN)
- Diğer Qundis su sayaçları
"""

import logging
import struct
import datetime
from typing import Dict, Optional, Any, List

from pymbus.src.telegram import Telegram
from pymbus.src.protocol import MBusProtocol, MBusDataRecord, DeviceType
from pymbus.src.drivers.driver_base import DriverBase

logger = logging.getLogger(__name__)

class QwaterDriver(DriverBase):
    """Qundis su sayaçları için sürücü sınıfı"""
    
    def __init__(self):
        """Qundis su sayacı sürücüsünü başlatır"""
        super().__init__()
        
        # Sürücü temel bilgileri
        self.name = "qwater"
        self.description = "Qundis water meter driver"
        
        # Desteklenen cihazlar
        self.manufacturer_codes = ["QDS"]  # Qundis
        self.meter_types = [DeviceType.WATER, DeviceType.COLD_WATER, DeviceType.HOT_WATER, DeviceType.WARM_WATER]  # 0x07, 0x12, 0x11, 0x06
        
        # Son okunan veriler
        self.last_readings = {}
    
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
            "meter": "qwater",
            "model": self._detect_model(telegram)
        }
        
        try:
            # Veri kayıtlarını işle
            for record in data_records:
                desc = record.get_description()
                value = record.parsed_value
                unit = record.get_unit()
                
                # Log ile hangi kayıtların işlendiğini görelim
                logger.debug(f"QwaterDriver: İşleme kaydı: {desc} = {value} {unit}")
                
                # Toplam hacim (su tüketimi)
                if desc == "Volume" and unit.startswith("m³"):
                    result["total_m3"] = value
                    
                # Akış hızı
                elif desc == "Volume Flow" and unit.startswith("m³/h"):
                    result["flow_m3h"] = value
                    
                # Sıcaklıklar
                elif desc in ["Flow Temperature", "Return Temperature", "External Temperature"] and unit.startswith("°C"):
                    field_name = desc.lower().replace(" ", "_")
                    result[field_name] = value
                    
                # Tarih/Zaman
                elif desc in ["Date", "Date and Time"]:
                    result["meter_time"] = value
            
            # Durum bilgisi
            status_info = self._parse_status_byte(telegram)
            if status_info:
                result.update(status_info)
                
            return result
            
        except Exception as e:
            logger.error(f"Veri ayrıştırma hatası: {e}", exc_info=True)
            return result  # Hataya rağmen toplanan bilgileri döndür

    def _detect_model(self, telegram: Telegram) -> str:
        """
        Telegram verilerinden cihaz modelini tespit eder
        
        Args:
            telegram: Telegram nesnesi
            
        Returns:
            str: Tespit edilen model adı
        """
        if not telegram or not telegram.header:
            return "Qundis Water Meter"
        
        # Versiyon kontrolü
        version = telegram.header.version
        
        # Versiyon numarasına göre model tayini
        if version == 0x01:
            return "Q water 5.5"
        elif version == 0x02:
            return "Q water S"
        elif version == 0x03:
            return "Q water Plus"
        
        # Modeli anlamak için telegram verilerine bak
        for record in MBusProtocol.parse_data_records(telegram.raw_data[10:]):
            # Üretim numarasına göre kontrol
            if record.get_description() == "Fabrication Number":
                fab_no = record.parsed_value
                if isinstance(fab_no, str):
                    if "QW" in fab_no:
                        return "Q water 5.5"
                    elif "QS" in fab_no:
                        return "Q water S"
                    elif "QP" in fab_no:
                        return "Q water Plus"
        
        # Model belirlenemedi
        return "Qundis Water Meter"
    
    def _parse_status_byte(self, telegram: Telegram) -> Dict[str, Any]:
        """
        Qundis durum baytını ayrıştırır
        
        Args:
            telegram: Telegram nesnesi
            
        Returns:
            Dict[str, Any]: Durum bilgileri
        """
        status = {}
        
        # Qundis su sayaçları için durum baytlarını incele
        try:
            if telegram and telegram.raw_data and len(telegram.raw_data) > 13:
                # Durum baytı konumu (genel olarak - cihaza özgü olabilir)
                status_byte = telegram.raw_data[13]
                
                # Durum bitlerini ayrıştır (Qundis spesifik)
                if status_byte & 0x01:
                    status["leak_detected"] = True
                
                if status_byte & 0x02:
                    status["reverse_flow"] = True
                
                if status_byte & 0x04:
                    status["burst_detected"] = True
                
                if status_byte & 0x08:
                    status["tamper_detected"] = True
                
                if status_byte & 0x10:
                    status["no_usage"] = True
                
                if status_byte & 0x20:
                    status["error_general"] = True
                
                # Genel durum mesajı
                status_text = []
                if "leak_detected" in status:
                    status_text.append("LEAK")
                if "reverse_flow" in status:
                    status_text.append("REVERSE")
                if "burst_detected" in status:
                    status_text.append("BURST")
                if "tamper_detected" in status:
                    status_text.append("TAMPER")
                if "no_usage" in status:
                    status_text.append("NO_USAGE")
                if "error_general" in status:
                    status_text.append("ERROR")
                
                if status_text:
                    status["status"] = " ".join(status_text)
                else:
                    status["status"] = "OK"
            
            return status
            
        except Exception as e:
            logger.error(f"Durum baytı ayrıştırma hatası: {e}")
            return {}
    
    def get_fields(self) -> List[Dict[str, Any]]:
        """
        Bu sürücü tarafından desteklenen alanların listesini döndürür
        
        Returns:
            List[Dict[str, Any]]: Alan bilgileri listesi
        """
        # Temel alanlar
        base_fields = super().get_fields()
        
        # Qundis'e özgü alanlar
        qwater_fields = [
            {
                "name": "total_m3",
                "description": "Total water consumption",
                "unit": "m³",
                "type": "float"
            },
            {
                "name": "last_month_m3",
                "description": "Last month water consumption",
                "unit": "m³",
                "type": "float"
            },
            {
                "name": "flow_m3h",
                "description": "Current flow rate",
                "unit": "m³/h",
                "type": "float"
            },
            {
                "name": "operating_time_h",
                "description": "Operating time",
                "unit": "h",
                "type": "float"
            },
            {
                "name": "meter_time",
                "description": "Meter time",
                "unit": None,
                "type": "datetime"
            },
            {
                "name": "status",
                "description": "Meter status",
                "unit": None,
                "type": "string"
            },
            {
                "name": "model",
                "description": "Meter model",
                "unit": None,
                "type": "string"
            }
        ]
        
        # Tüm alanları birleştir
        return base_fields + qwater_fields