"""
Genişletilmiş M-Bus protokol uygulaması

Tam M-Bus/WMBus protokol desteği sağlayan gelişmiş protokol modülü.
Tüm telegram tipleri, veri yapıları ve alanları için destek.
"""
from enum import Enum, IntEnum, IntFlag
from typing import Dict, List, Optional, Tuple, Union, Any, Set
import logging
import struct
import datetime
import binascii

from Crypto.Cipher import AES
from pymbus.src.utils.encryption import decrypt_aes_cbc
from pymbus.src.utils.encryption import decrypt_aes_cbc, decrypt_aes_cmac, CRYPTO_AVAILABLE

logger = logging.getLogger(__name__)

class LinkMode(Enum):
    """Desteklenen M-Bus link modları"""
    S1 = "S1"  # Stationary mode 1
    S1M = "S1M"  # Stationary mode 1, alternative
    S2 = "S2"  # Stationary mode 2
    T1 = "T1"  # Frequent transmit mode 1
    T2 = "T2"  # Frequent transmit mode 2
    C1 = "C1"  # Compact mode 1
    C2 = "C2"  # Compact mode 2
    F1 = "F1"  # Frequent transmit mode extended frame format
    F2 = "F2"  # Compact mode extended frame format
    MBUS = "MBUS"  # Wired M-Bus


class DeviceType(IntEnum):
    """M-Bus cihaz tipleri (EN 13757-3)"""
    OTHER = 0x00
    OIL = 0x01
    ELECTRICITY = 0x02
    GAS = 0x03
    HEAT = 0x04
    STEAM = 0x05
    WARM_WATER = 0x06
    WATER = 0x07
    HEAT_COST_ALLOCATOR = 0x08
    COMPRESSED_AIR = 0x09
    COOLING_LOAD_METER = 0x0A
    COOLING_LOAD_METER_INLET = 0x0B
    HEAT_INLET = 0x0C
    HEAT_COOLING_LOAD_METER = 0x0D
    BUS_SYSTEM_COMPONENT = 0x0E
    UNKNOWN = 0x0F
    CALORIFIC_VALUE = 0x10
    HOT_WATER = 0x11
    COLD_WATER = 0x12
    DUAL_WATER = 0x13
    PRESSURE = 0x14
    AD_CONVERTER = 0x15
    SMOKE_DETECTOR = 0x16
    ROOM_SENSOR = 0x17
    GAS_DETECTOR = 0x18
    BREAKER = 0x19
    VALVE = 0x1A
    CUSTOMER_UNIT = 0x1B
    WASTE_METER = 0x1C
    GARBAGE = 0x1D
    COMMUNICATION_CONTROLLER = 0x1E
    UNIDIRECTIONAL_REPEATER = 0x1F
    BIDIRECTIONAL_REPEATER = 0x20
    RADIO_CONVERTER_SYSTEM_SIDE = 0x21
    RADIO_CONVERTER_METER_SIDE = 0x22
    BROADCASTING_ACTUATOR = 0x23
    SUB_DEVICE = 0x24
    MULTI_UTILITY_COMMUNICATION_CONTROLLER = 0x25
    # Yeni cihaz tipleri buraya eklenebilir


class FunctionCode(IntEnum):
    """M-Bus Function Codes (Control field C)"""
    SND_NKE = 0x40  # Reset remote link
    SND_UD = 0x53    # Send user data
    REQ_UD1 = 0x5A   # Request user data class 1
    REQ_UD2 = 0x5B   # Request user data class 2
    RSP_UD = 0x08    # Response user data
    # İlave kodlar


class ControlInformation(IntEnum):
    """M-Bus Control Information (CI field)"""
    STANDARD_DATA = 0x72      # EN 13757-3 standart veri
    EXTENDED_DATA = 0x7A      # EN 13757-3 genişletilmiş veri
    MBUS_SHORT_HEADER = 0x8C  # M-Bus kısa başlık
    MBUS_LONG_HEADER = 0x8D   # M-Bus uzun başlık
    MANUFACTURER_DATA = 0x7F  # Üretici özel veri
    # İlave CI alan kodları


class DIB_VIB(IntFlag):
    """Data Information Block / Value Information Block bit maskeleri"""
    # DIF bitleri
    DIF_EXTENSION = 0x80        # DIF uzatma biti
    DIF_FUNCTION_MASK = 0x30    # DIF fonksiyon maskesi
    DIF_DATA_MASK = 0x0F        # DIF veri maskesi
    
    # DIFE bitleri
    DIFE_EXTENSION = 0x80       # DIFE uzatma biti
    DIFE_DEVICE = 0x40          # DIFE cihaz biti
    DIFE_TARIFF_MASK = 0x30     # DIFE tarife maskesi
    DIFE_STORAGE_NO_MASK = 0x0F # DIFE depolama numarası maskesi
    
    # VIF bitleri
    VIF_EXTENSION = 0x80        # VIF uzatma biti
    VIF_VALUE_MASK = 0x7F       # VIF değer maskesi


class DIF(IntEnum):
    """Data Information Field (DIF) değerleri"""
    NO_DATA = 0x00
    INT8 = 0x01
    INT16 = 0x02
    INT24 = 0x03
    INT32 = 0x04
    FLOAT32 = 0x05
    INT48 = 0x06
    INT64 = 0x07
    SELECTION_FOR_READOUT = 0x08
    SPECIAL_FUNCTION = 0x09
    SPECIAL_FUNCTION_GLOBAL_READOUT = 0x0A
    STRING_VARIABLE = 0x0B
    PRIMARY_VALUE = 0x0C
    SPECIAL_FUNCTION_GLOBAL_READOUT2 = 0x0D
    SPECIAL_FUNCTION_IDLE_FILLER = 0x0F
    INT_BCD8 = 0x10
    INT_BCD16 = 0x11
    INT_BCD24 = 0x12
    INT_BCD32 = 0x13
    FLOAT_BCD32 = 0x14
    INT_BCD48 = 0x15
    INT_BCD64 = 0x16
    VARIABLE_LENGTH = 0x17
    MAN_SPEC_DATA = 0x0F


class VIF(IntEnum):
    """Value Information Field (VIF) değerleri"""
    ENERGY_WH = 0x00        # E = 10ⁿ Wh
    ENERGY_J = 0x08         # E = 10ⁿ J
    VOLUME = 0x10           # V = 10ⁿ m³
    MASS = 0x18             # M = 10ⁿ kg
    ON_TIME = 0x20          # t = s
    OPERATING_TIME = 0x28   # t = s
    POWER_W = 0x30          # P = 10ⁿ W
    POWER_J_H = 0x38        # P = 10ⁿ J/h
    VOLUME_FLOW = 0x40      # V = 10ⁿ m³/h
    VOLUME_FLOW_EXT = 0x48  # V = 10ⁿ m³/min
    VOLUME_FLOW_EXT2 = 0x50 # V = 10ⁿ m³/s
    MASS_FLOW = 0x58        # M = 10ⁿ kg/h
    FLOW_TEMPERATURE = 0x60 # T = 10ⁿ °C
    RETURN_TEMPERATURE = 0x68 # T = 10ⁿ °C
    TEMPERATURE_DIFF = 0x70 # ΔT = 10ⁿ K
    EXTERNAL_TEMP = 0x78    # T = 10ⁿ °C
    PRESSURE = 0x80         # p = 10ⁿ bar
    DATE = 0xA8             # Tarih
    DATETIME = 0xB0         # Tarih ve saat
    HCA = 0xC0              # H.C.A.
    MANUFACTURER_SPECIFIC = 0xF0  # Üretici özel
    FABRICATION_NO = 0xFD   # Üretim no
    ENHANCED_VIF = 0xFB     # Gelişmiş VIF
    # İlave VIF kodları


class MBusStatus(IntFlag):
    """M-Bus Durum Bayrakları"""
    NORMAL = 0               # Normal durum 
    POWER_LOW = 1            # Düşük pil 
    ERROR_GENERAL = 2        # Genel hata
    ERROR_PERMANENT = 4      # Kalıcı hata
    ERROR_TEMPORARY = 8      # Geçici hata
    LEAK_DETECTED = 16       # Sızıntı algılandı
    REVERSE_FLOW = 32        # Ters akış
    OVERFLOW = 64            # Taşma
    TAMPER_DETECTED = 128    # Müdahale algılandı
    NO_COMMUNICATION = 256   # İletişim yok
    MBUS_READOUT_ERROR = 512 # M-Bus okuma hatası
    # İlave durum bayrakları


class MBusDataRecord:
    """M-Bus veri kaydı"""
    
    def __init__(self, dif: int, vif: int, value: bytes, 
                storage_number: int = 0, tariff: int = 0, 
                subunit: int = 0, function: int = 0):
        """
        Args:
            dif: Data Information Field
            vif: Value Information Field
            value: Değer verisi
            storage_number: Depolama numarası
            tariff: Tarife numarası
            subunit: Alt birim numarası
            function: Fonksiyon tipi
        """
        self.dif = dif
        self.vif = vif
        self.value = value
        self.storage_number = storage_number
        self.tariff = tariff
        self.subunit = subunit
        self.function = function
        self.dife_data = []
        self.vife_data = []
        self.parsed_value = None
        self._parse_value()
    
    def _parse_value(self) -> None:
        """Veri tipine göre değeri ayrıştırır"""
        try:
            # DIF'e göre değeri ayrıştır
            if self.dif == DIF.NO_DATA:
                self.parsed_value = None
            elif self.dif == DIF.INT8:
                self.parsed_value = struct.unpack("<b", self.value)[0]
            elif self.dif == DIF.INT16:
                self.parsed_value = struct.unpack("<h", self.value)[0]
            elif self.dif == DIF.INT24:
                # 24-bit integer için özel işlem
                value_int = int.from_bytes(self.value, byteorder='little', signed=True)
                # 24-bit işaretli değer kontrolü (2's complement)
                if value_int & 0x800000:
                    # Negatif değer
                    value_int = value_int - 0x1000000
                self.parsed_value = value_int
            elif self.dif == DIF.INT32:
                self.parsed_value = struct.unpack("<i", self.value)[0]
            elif self.dif == DIF.FLOAT32:
                self.parsed_value = struct.unpack("<f", self.value)[0]
            elif self.dif == DIF.INT48:
                # 48-bit integer için özel işlem
                value_int = int.from_bytes(self.value, byteorder='little', signed=True)
                # 48-bit işaretli değer kontrolü (2's complement)
                if value_int & 0x800000000000:
                    # Negatif değer
                    value_int = value_int - 0x1000000000000
                self.parsed_value = value_int
            elif self.dif == DIF.INT64:
                self.parsed_value = struct.unpack("<q", self.value)[0]
            elif self.dif == DIF.INT_BCD8:
                # BCD formatında değer
                bcd = int(self.value.hex(), 16)
                self.parsed_value = self._decode_bcd(bcd, 2)
            elif self.dif == DIF.INT_BCD16:
                bcd = int(self.value.hex(), 16)
                self.parsed_value = self._decode_bcd(bcd, 4)
            elif self.dif == DIF.INT_BCD24:
                bcd = int(self.value.hex(), 16)
                self.parsed_value = self._decode_bcd(bcd, 6)
            elif self.dif == DIF.INT_BCD32:
                bcd = int(self.value.hex(), 16)
                self.parsed_value = self._decode_bcd(bcd, 8)
            elif self.dif == DIF.VARIABLE_LENGTH:
                # Değişken uzunluklu değer
                if len(self.value) > 0:
                    length = self.value[0]
                    if length + 1 <= len(self.value):
                        self.parsed_value = self.value[1:length+1]
                    else:
                        self.parsed_value = self.value[1:]
                else:
                    self.parsed_value = self.value
            elif self.dif == DIF.STRING_VARIABLE:
                # String değeri
                try:
                    self.parsed_value = self.value.decode('utf-8')
                except UnicodeDecodeError:
                    # UTF-8 deşifreleme başarısız olursa ASCII dene
                    try:
                        self.parsed_value = self.value.decode('ascii', errors='replace')
                    except:
                        # Hiçbir şekilde çözülemezse hex olarak göster
                        self.parsed_value = self.value.hex()
            else:
                # Bilinmeyen DIF için ham veri
                self.parsed_value = self.value.hex()
                
            # VIF spesifik işleme
            if self.vif == VIF.DATE and len(self.value) >= 2:
                # Tarih ayrıştırması
                self.parsed_value = self._parse_date(self.value)
            elif self.vif == VIF.DATETIME and len(self.value) >= 4:
                # Tarih ve saat ayrıştırması
                self.parsed_value = self._parse_datetime(self.value)
                
        except Exception as e:
            logger.error(f"Değer ayrıştırma hatası: {e}")
            # Hata durumunda hex göster
            self.parsed_value = self.value.hex()
    
    def _decode_bcd(self, value: int, digits: int) -> int:
        """
        BCD değerini desimel değere dönüştürür
        
        Args:
            value: BCD değeri
            digits: Basamak sayısı
            
        Returns:
            int: Desimel değer
        """
        result = 0
        multiplier = 1
        
        for _ in range(digits):
            digit = value & 0x0F
            if digit > 9:
                logger.warning(f"Geçersiz BCD basamağı: {digit}")
                digit = 9  # Geçersiz basamağı 9 ile sınırla
            
            result += digit * multiplier
            multiplier *= 10
            value >>= 4
            
        return result
    
    def _parse_date(self, data: bytes) -> str:
        """
        M-Bus tarih formatını ayrıştırır (EN13757-3)
        
        Args:
            data: Tarih verisi (2 byte)
            
        Returns:
            str: YYYY-MM-DD formatında tarih
        """
        if len(data) < 2:
            return "Invalid date data"
            
        day = data[0] & 0x1F
        month = ((data[1] & 0x0F) | ((data[0] & 0xE0) >> 5))
        year = 2000 + ((data[1] & 0xF0) >> 4)
        
        # Tarih doğrulama
        if month < 1 or month > 12 or day < 1 or day > 31:
            logger.warning(f"Geçersiz tarih: {day}.{month}.{year}")
            return f"{year:04d}-{month:02d}-{day:02d} (Geçersiz)"
            
        return f"{year:04d}-{month:02d}-{day:02d}"
    
    def _parse_datetime(self, data: bytes) -> str:
        """
        M-Bus tarih ve saat formatını ayrıştırır
        
        Args:
            data: Tarih ve saat verisi (4 byte)
            
        Returns:
            str: YYYY-MM-DD HH:MM:SS formatında tarih ve saat
        """
        if len(data) < 4:
            return "Invalid datetime data"
            
        date_str = self._parse_date(data[:2])
        
        minute = data[2] & 0x3F
        hour = data[3] & 0x1F
        
        # Saat doğrulama
        if hour > 23 or minute > 59:
            logger.warning(f"Geçersiz saat: {hour}:{minute}")
            return f"{date_str} {hour:02d}:{minute:02d} (Geçersiz)"
            
        return f"{date_str} {hour:02d}:{minute:02d}"
    
    def get_unit(self) -> str:
        """
        VIF alanına göre birim döndürür
        
        Returns:
            str: Birim string'i
        """
        vif_without_extension = self.vif & 0x7F
        exponent = vif_without_extension & 0x07  # Son 3 bit eksponent
        
        # VIF başlık değerine göre birim tayini
        if (vif_without_extension & 0xF8) == 0x00:  # ENERGY_WH
            multiplier = 10 ** (exponent - 3)
            return f"Wh{self._format_multiplier(multiplier)}"
        elif (vif_without_extension & 0xF8) == 0x08:  # ENERGY_J
            multiplier = 10 ** (exponent - 3)
            return f"J{self._format_multiplier(multiplier)}"
        elif (vif_without_extension & 0xF8) == 0x10:  # VOLUME
            multiplier = 10 ** (exponent - 6)
            return f"m³{self._format_multiplier(multiplier)}"
        elif (vif_without_extension & 0xF8) == 0x18:  # MASS
            multiplier = 10 ** (exponent - 3)
            return f"kg{self._format_multiplier(multiplier)}"
        elif (vif_without_extension & 0xF8) == 0x20:  # ON_TIME
            if exponent == 0:
                return "s"
            elif exponent == 1:
                return "min"
            elif exponent == 2:
                return "h"
            elif exponent == 3:
                return "day"
            else:
                return f"s·10^{exponent}"
        elif (vif_without_extension & 0xF8) == 0x28:  # OPERATING_TIME
            if exponent == 0:
                return "s"
            elif exponent == 1:
                return "min"
            elif exponent == 2:
                return "h"
            elif exponent == 3:
                return "day"
            else:
                return f"s·10^{exponent}"
        elif (vif_without_extension & 0xF8) == 0x30:  # POWER_W
            multiplier = 10 ** (exponent - 3)
            return f"W{self._format_multiplier(multiplier)}"
        elif (vif_without_extension & 0xF8) == 0x38:  # POWER_J_H
            multiplier = 10 ** (exponent - 3)
            return f"J/h{self._format_multiplier(multiplier)}"
        elif (vif_without_extension & 0xF8) == 0x40:  # VOLUME_FLOW
            multiplier = 10 ** (exponent - 6)
            return f"m³/h{self._format_multiplier(multiplier)}"
        elif (vif_without_extension & 0xF8) == 0x48:  # VOLUME_FLOW_EXT
            multiplier = 10 ** (exponent - 7)
            return f"m³/min{self._format_multiplier(multiplier)}"
        elif (vif_without_extension & 0xF8) == 0x50:  # VOLUME_FLOW_EXT2
            multiplier = 10 ** (exponent - 9)
            return f"m³/s{self._format_multiplier(multiplier)}"
        elif (vif_without_extension & 0xF8) == 0x58:  # MASS_FLOW
            multiplier = 10 ** (exponent - 3)
            return f"kg/h{self._format_multiplier(multiplier)}"
        elif (vif_without_extension & 0xF8) == 0x60:  # FLOW_TEMPERATURE
            multiplier = 10 ** (exponent - 3)
            return f"°C{self._format_multiplier(multiplier)}"
        elif (vif_without_extension & 0xF8) == 0x68:  # RETURN_TEMPERATURE
            multiplier = 10 ** (exponent - 3)
            return f"°C{self._format_multiplier(multiplier)}"
        elif (vif_without_extension & 0xF8) == 0x70:  # TEMPERATURE_DIFF
            multiplier = 10 ** (exponent - 3)
            return f"K{self._format_multiplier(multiplier)}"
        elif (vif_without_extension & 0xF8) == 0x78:  # EXTERNAL_TEMP
            multiplier = 10 ** (exponent - 3)
            return f"°C{self._format_multiplier(multiplier)}"
        elif (vif_without_extension & 0xF8) == 0x80:  # PRESSURE
            multiplier = 10 ** (exponent - 3)
            return f"bar{self._format_multiplier(multiplier)}"
        elif vif_without_extension == VIF.DATE:
            return "date"
        elif vif_without_extension == VIF.DATETIME:
            return "datetime"
        elif (vif_without_extension & 0xF0) == 0xC0:  # HCA
            return "HCA"
        elif vif_without_extension == VIF.MANUFACTURER_SPECIFIC:
            return "manufacturer specific"
        else:
            return ""
    
    def _format_multiplier(self, multiplier: float) -> str:
        """
        Birim çarpanını biçimlendirir
        
        Args:
            multiplier: Çarpan değeri
            
        Returns:
            str: Biçimlendirilmiş çarpan
        """
        if multiplier == 1:
            return ""
        elif multiplier > 1:
            # Integer kontrolü için is_integer yerine basit tip kontrolü kullan
            if isinstance(multiplier, int):
                return f"·{multiplier}"
            elif isinstance(multiplier, float) and multiplier.is_integer():
                return f"·{int(multiplier)}"
            else:
                return f"·{multiplier}"
        else:
            # 1'den küçük çarpanlar için ön ek kullan
            if multiplier == 0.001:
                return "m"  # mili
            elif multiplier == 0.000001:
                return "µ"  # mikro
            elif multiplier == 0.000000001:
                return "n"  # nano
            elif multiplier == 1000:
                return "k"  # kilo
            elif multiplier == 1000000:
                return "M"  # mega
            elif multiplier == 1000000000:
                return "G"  # giga
            else:
                return f"·{multiplier}"

    def get_description(self) -> str:
        """
        VIF alanına göre açıklama döndürür
        
        Returns:
            str: Açıklama metni
        """
        vif_without_extension = self.vif & 0x7F
        
        # VIF değerine göre açıklama oluştur
        if (vif_without_extension & 0xF8) == 0x00:  # ENERGY_WH
            return "Energy"
        elif (vif_without_extension & 0xF8) == 0x08:  # ENERGY_J
            return "Energy"
        elif (vif_without_extension & 0xF8) == 0x10:  # VOLUME
            return "Volume"
        elif (vif_without_extension & 0xF8) == 0x18:  # MASS
            return "Mass"
        elif (vif_without_extension & 0xF8) == 0x20:  # ON_TIME
            return "On Time"
        elif (vif_without_extension & 0xF8) == 0x28:  # OPERATING_TIME
            return "Operating Time"
        elif (vif_without_extension & 0xF8) == 0x30:  # POWER_W
            return "Power"
        elif (vif_without_extension & 0xF8) == 0x38:  # POWER_J_H
            return "Power"
        elif (vif_without_extension & 0xF8) == 0x40:  # VOLUME_FLOW
            return "Volume Flow"
        elif (vif_without_extension & 0xF8) == 0x48:  # VOLUME_FLOW_EXT
            return "Volume Flow"
        elif (vif_without_extension & 0xF8) == 0x50:  # VOLUME_FLOW_EXT2
            return "Volume Flow"
        elif (vif_without_extension & 0xF8) == 0x58:  # MASS_FLOW
            return "Mass Flow"
        elif (vif_without_extension & 0xF8) == 0x60:  # FLOW_TEMPERATURE
            return "Flow Temperature"
        elif (vif_without_extension & 0xF8) == 0x68:  # RETURN_TEMPERATURE
            return "Return Temperature"
        elif (vif_without_extension & 0xF8) == 0x70:  # TEMPERATURE_DIFF
            return "Temperature Difference"
        elif (vif_without_extension & 0xF8) == 0x78:  # EXTERNAL_TEMP
            return "External Temperature"
        elif (vif_without_extension & 0xF8) == 0x80:  # PRESSURE
            return "Pressure"
        elif vif_without_extension == VIF.DATE:
            return "Date"
        elif vif_without_extension == VIF.DATETIME:
            return "Date and Time"
        elif (vif_without_extension & 0xF0) == 0xC0:  # HCA
            return "Heat Cost Allocation"
        elif vif_without_extension == VIF.MANUFACTURER_SPECIFIC:
            return "Manufacturer Specific"
        elif vif_without_extension == VIF.FABRICATION_NO:
            return "Fabrication Number"
        else:
            return f"Unknown VIF: 0x{vif_without_extension:02x}"

    def get_storage_info(self) -> str:
        """
        Depolama bilgilerini döndürür
        
        Returns:
            str: Depolama bilgisi
        """
        if self.storage_number == 0:
            return "Current value"
        else:
            return f"Storage {self.storage_number}"
    
    def get_tariff_info(self) -> str:
        """
        Tarife bilgilerini döndürür
        
        Returns:
            str: Tarife bilgisi
        """
        if self.tariff == 0:
            return "No tariff"
        else:
            return f"Tariff {self.tariff}"
    
    def get_function_description(self) -> str:
        """
        Fonksiyon bilgilerini döndürür
        
        Returns:
            str: Fonksiyon açıklaması
        """
        function_codes = {
            0: "Instantaneous value",
            1: "Maximum value",
            2: "Minimum value",
            3: "Value during error state"
        }
        return function_codes.get(self.function, f"Unknown function: {self.function}")
    
    def __str__(self) -> str:
        """İnsan okunabilir temsil"""
        info = []
        
        # Temel bilgiler
        info.append(f"{self.get_description()}: {self.parsed_value} {self.get_unit()}")
        
        # Ek bilgiler
        if self.storage_number != 0:
            info.append(f"Storage: {self.storage_number}")
        if self.tariff != 0:
            info.append(f"Tariff: {self.tariff}")
        if self.function != 0:
            info.append(f"Function: {self.get_function_description()}")
        
        return ", ".join(info)


class MBusProtocol:
    """M-Bus protokol işlemleri için yardımcı sınıf"""
    
    # OMS versiyon
    OMS_VERSION_10 = 10
    OMS_VERSION_11 = 11
    OMS_VERSION_12 = 12
    OMS_VERSION_20 = 20
    OMS_VERSION_30 = 30
    OMS_VERSION_40 = 40
    
    @staticmethod
    def parse_data_records(data: bytes) -> List[MBusDataRecord]:
        """
        Ham veriden veri kayıtlarını ayrıştırır
        
        Args:
            data: Ayrıştırılacak veri
            
        Returns:
            List[MBusDataRecord]: Ayrıştırılan veri kayıtları listesi
        """
        records = []
        
        # En az 1 bayt veri gerekli
        if not data or len(data) < 1:
            return records
            
        i = 0
        while i < len(data):
            try:
                # DIF alanını oku
                dif = data[i]
                i += 1
                
                # Başlangıç DIF değerini kaydet
                dif_value = dif & 0x0F
                function = (dif & 0x30) >> 4
                
                # DIFE varsa işle
                dife_bytes = []
                storage_number = 0
                tariff = 0
                device = 0
                
                while dif & 0x80:
                    if i >= len(data):
                        logger.debug("DIF uzantısı bekleniyor ancak veri bitti")
                        break
                        
                    dife = data[i]
                    dife_bytes.append(dife)
                    i += 1
                    
                    # DIFE alanını işle
                    # Depolama numarası (LSB'ler önce, 4 bit her DIFE'de)
                    storage_number |= (dife & 0x0F) << (len(dife_bytes) - 1) * 4
                    
                    # Tarife numarası (2 bit her DIFE'de)
                    tariff |= ((dife & 0x30) >> 4) << (len(dife_bytes) - 1) * 2
                    
                    # Cihaz biti
                    if dife & 0x40:
                        device = 1
                        
                    # İlave DIFE'ler varsa devam et
                    if not (dife & 0x80):
                        break
                
                # VIF alanını oku
                if i >= len(data):
                    logger.debug("VIF bekleniyor ancak veri bitti")
                    break
                    
                vif = data[i]
                i += 1
                
                # VIFE varsa işle
                vife_bytes = []
                while vif & 0x80:
                    if i >= len(data):
                        logger.debug("VIF uzantısı bekleniyor ancak veri bitti")
                        break
                        
                    vife = data[i]
                    vife_bytes.append(vife)
                    i += 1
                    
                    # İlave VIFE'ler varsa devam et
                    if not (vife & 0x80):
                        break
                
                # VIF'i çözümle
                vif_value = vif & 0x7F
                
                # Veri uzunluğunu hesapla
                length = MBusProtocol._get_data_length(dif_value)
                
                # Değişken uzunluklu veri alanını işle
                if dif_value == DIF.VARIABLE_LENGTH or dif_value == DIF.STRING_VARIABLE:
                    if i < len(data):
                        # İlk byte uzunluğu belirtir
                        length = data[i] + 1  # +1 uzunluk baytı için
                        
                # Veri sınırlarını kontrol et
                if i + length > len(data):
                    logger.warning(f"Veri kaydı alanı sınırları aşıyor: {i}+{length} > {len(data)}")
                    break
                
                # Veriyi çıkar
                value = data[i:i+length]
                i += length
                
                # Veri kaydını ekle
                record = MBusDataRecord(
                    dif=dif_value, 
                    vif=vif_value, 
                    value=value,
                    storage_number=storage_number,
                    tariff=tariff,
                    subunit=device,
                    function=function
                )
                
                # DIFE ve VIFE verilerini ekle
                record.dife_data = dife_bytes
                record.vife_data = vife_bytes
                
                records.append(record)
                
                # Değerlendirme için kayıt bilgisini logla
                logger.debug(f"Veri kaydı: DIF=0x{dif_value:02x}, "
                            f"VIF=0x{vif_value:02x}, "
                            f"STO={storage_number}, "
                            f"TARIFF={tariff}, "
                            f"Value={record.parsed_value} {record.get_unit()}")
                
            except IndexError as e:
                logger.error(f"Veri kaydı ayrıştırma hatası: {e}")
                break
                
        return records
    
    @staticmethod
    def _get_data_length(dif: int) -> int:
        """
        DIF alanına göre veri uzunluğunu belirler
        
        Args:
            dif: Data Information Field değeri
            
        Returns:
            int: Veri uzunluğu (byte cinsinden)
        """
        dif_lengths = {
            DIF.NO_DATA: 0,
            DIF.INT8: 1,
            DIF.INT16: 2,
            DIF.INT24: 3,
            DIF.INT32: 4,
            DIF.FLOAT32: 4,
            DIF.INT48: 6,
            DIF.INT64: 8,
            DIF.SELECTION_FOR_READOUT: 1,
            DIF.INT_BCD8: 1,
            DIF.INT_BCD16: 2,
            DIF.INT_BCD24: 3,
            DIF.INT_BCD32: 4,
            DIF.FLOAT_BCD32: 4,
            DIF.INT_BCD48: 6,
            DIF.INT_BCD64: 8,
            DIF.VARIABLE_LENGTH: 1,  # İlk byte uzunluğu gösterir, ayrı olarak işlenmeli
            DIF.STRING_VARIABLE: 1,  # İlk byte uzunluğu gösterir, ayrı olarak işlenmeli
            DIF.PRIMARY_VALUE: 0     # Değişken uzunluklu, bağlama bağlı
        }
        
        return dif_lengths.get(dif, 0)
            
    @staticmethod
    def check_crc(data: bytes) -> bool:
        """
        Telegram CRC kontrolü yapar
        
        Args:
            data: Kontrol edilecek veri
            
        Returns:
            bool: CRC doğru mu?
        """
        # M-Bus protokolü CRC hesaplama
        if len(data) < 3:
            return False
            
        # İlk iki byte veri, üçüncü byte CRC
        crc = MBusProtocol.calculate_crc(data[:-1])
        return crc == data[-1]
    
    @staticmethod
    def calculate_crc(data: bytes) -> int:
        """
        M-Bus CRC hesaplama (EN 13757-3)
        
        Args:
            data: CRC hesaplanacak veri
            
        Returns:
            int: Hesaplanan CRC
        """
        crc = 0
        
        for b in data:
            # Polinomla XOR
            crc ^= b
            
            # 8 bit işlem
            for _ in range(8):
                # En düşük bit 1 ise
                if crc & 0x01:
                    # Polinomla XOR (M-Bus polinomu: x^8 + x^5 + x^4 + 1)
                    crc = (crc >> 1) ^ 0x8C
                else:
                    # Sağa kaydır
                    crc = crc >> 1
        
        return crc

    @staticmethod
    def decode_manufacturer(code: int) -> str:
        """
        Üretici kodunu 3 harfli koda dönüştürür
        
        Args:
            code: 16-bit üretici kodu
            
        Returns:
            str: 3 karakterli üretici kodu
        """
        # M-Bus protokolüne göre üretici kodu dönüşümü
        # Her 5 bit bir karakter için kullanılır, 3 karakter
        char1 = ((code >> 10) & 0x1F) + 64
        char2 = ((code >> 5) & 0x1F) + 64
        char3 = (code & 0x1F) + 64
        return chr(char1) + chr(char2) + chr(char3)
    
    @staticmethod
    def encode_manufacturer(code: str) -> int:
        """
        3 harfli kodu üretici koduna dönüştürür
        
        Args:
            code: 3 karakterli üretici kodu
            
        Returns:
            int: 16-bit üretici kodu
        """
        if len(code) != 3:
            raise ValueError("Üretici kodu 3 karakter olmalıdır")
            
        # Karakter kodlarını 5 bitlik değerlere dönüştür
        c1 = ord(code[0]) - 64
        c2 = ord(code[1]) - 64
        c3 = ord(code[2]) - 64
        
        # 16-bit üretici kodunu oluştur
        return (c1 << 10) | (c2 << 5) | c3
    
    @staticmethod
    def decode_device_type(code: int) -> str:
        """
        Cihaz tipi kodunu açıklamaya dönüştürür
        
        Args:
            code: Cihaz tipi kodu
            
        Returns:
            str: Cihaz tipi açıklaması
        """
        try:
            return DeviceType(code).name.lower().replace('_', ' ')
        except ValueError:
            return f"unknown (0x{code:02x})"
    
    @staticmethod
    def get_status_info(status_byte: int) -> Dict[str, Any]:
        """
        Durum baytını ayrıştırır
        
        Args:
            status_byte: Durum baytı
            
        Returns:
            Dict[str, Any]: Durum bilgileri
        """
        result = {}
        
        # Durum bayraklarını kontrol et
        if status_byte & MBusStatus.POWER_LOW:
            result["power_low"] = True
            
        if status_byte & MBusStatus.ERROR_GENERAL:
            result["error"] = True
            
        if status_byte & MBusStatus.ERROR_PERMANENT:
            result["permanent_error"] = True
            
        if status_byte & MBusStatus.ERROR_TEMPORARY:
            result["temporary_error"] = True
            
        if status_byte & MBusStatus.LEAK_DETECTED:
            result["leak_detected"] = True
            
        if status_byte & MBusStatus.REVERSE_FLOW:
            result["reverse_flow"] = True
            
        if status_byte & MBusStatus.OVERFLOW:
            result["overflow"] = True
            
        if status_byte & MBusStatus.TAMPER_DETECTED:
            result["tamper_detected"] = True
        
        # Özet durum metni
        status_text = []
        
        if "power_low" in result:
            status_text.append("POWER_LOW")
            
        if "error" in result:
            status_text.append("ERROR")
            
        if "permanent_error" in result:
            status_text.append("PERMANENT_ERROR")
            
        if "temporary_error" in result:
            status_text.append("TEMP_ERROR")
            
        if "leak_detected" in result:
            status_text.append("LEAK")
            
        if "reverse_flow" in result:
            status_text.append("REVERSE")
            
        if "overflow" in result:
            status_text.append("OVERFLOW")
            
        if "tamper_detected" in result:
            status_text.append("TAMPER")
            
        if status_text:
            result["status"] = " ".join(status_text)
        else:
            result["status"] = "OK"
            
        return result

    @staticmethod
    def analyze_telegram(data: bytes) -> Dict[str, Any]:
        """
        Telegram'ı analiz eder ve sürücü önerisi yapar
        
        Args:
            data: Ayrıştırılacak veri
            
        Returns:
            Dict[str, Any]: Analiz sonuçları
        """
        result = {
            "valid": False,
            "length": len(data),
            "mfct": None,
            "id": None,
            "version": None,
            "type": None,
            "ci_field": None,
            "encrypted": False,
            "records": [],
            "suggested_drivers": []
        }
        
        # Minimum uzunluk kontrolü
        if len(data) < 10:
            result["error"] = "Telegram çok kısa"
            return result
            
        try:
            # Telegram başlığını ayrıştır
            if data[0] == 0x68 and len(data) >= 9:
                # Uzun başlık
                length1 = data[1]
                length2 = data[2]
                
                if length1 != length2 or data[3] != 0x68:
                    result["error"] = "Geçersiz uzun başlık formatı"
                    return result
                    
                # Kontrol alanı
                result["control"] = data[4]
                
                # Adres
                result["id"] = f"{data[5]:02x}{data[6]:02x}{data[7]:02x}{data[8]:02x}"
                
                # CI alanı
                if len(data) > 9:
                    result["ci_field"] = data[9]
                    
                # Uzunluk kontrolü
                if len(data) < length1 + 6:
                    result["error"] = "Telegram uzunluğu geçersiz"
                    return result
                    
            elif data[0] == 0x44:
                # Kısa başlık (WMBus)
                if len(data) < 10:
                    result["error"] = "Telegram çok kısa"
                    return result
                    
                # L-field
                l_field = data[0]
                
                # C-field
                result["control"] = data[1]
                result["encrypted"] = (result["control"] & 0x05) > 0
                
                # M-field (üretici kodu)
                manufacturer_code = (data[3] << 8) | data[2]
                result["mfct"] = MBusProtocol.decode_manufacturer(manufacturer_code)
                
                # A-field (sayaç kimliği)
                id_bytes = data[4:8]
                result["id"] = ''.join(f'{b:02x}' for b in reversed(id_bytes))
                
                # Version
                result["version"] = data[8]
                
                # Device type
                result["type"] = data[9]
                result["type_name"] = MBusProtocol.decode_device_type(data[9])
                
                # CI alanı (varsa)
                if len(data) > 10:
                    result["ci_field"] = data[10]
                
                # Başarılı ayrıştırma
                result["valid"] = True
                
                # Veri alanını analiz et
                if len(data) > 11 and not result["encrypted"]:
                    # Veri alanını ayrıştırmayı dene
                    records = MBusProtocol.parse_data_records(data[11:])
                    
                    # Kayıtları ekle
                    for record in records:
                        record_info = {
                            "description": record.get_description(),
                            "value": record.parsed_value,
                            "unit": record.get_unit(),
                            "storage": record.storage_number,
                            "tariff": record.tariff,
                            "function": record.get_function_description()
                        }
                        result["records"].append(record_info)
                        
            else:
                result["error"] = "Tanınmayan telegram formatı"
                return result
                
            # Sürücü önerileri
            if result["valid"] and result["mfct"] and result["type"] is not None:
                # Üretici ve tipine göre sürücü öner
                # Bu kısım, eldeki sürücü veritabanına göre doldurulmalı
                driver_mapping = {
                    # Üretici, Tip, Versiyon -> Sürücü adı
                    ("KAM", 0x07): "kamwater",      # Kamstrup su sayacı
                    ("KAM", 0x04): "kamheat",       # Kamstrup ısı sayacı
                    ("DME", 0x07): "hydrus",        # Diehl Hydrus su sayacı
                    ("DME", 0x06): "hydrodigit",    # BMeters Hydrodigit sıcak su sayacı
                    ("LAS", 0x17): "lansenth",      # Lansen sıcaklık sensörü
                    ("ELS", 0x02): "omnipower",     # Kamstrup Omnipower elektrik sayacı
                    ("TCH", 0x04): "compact5",      # Techem compact V ısı sayacı
                    ("QDS", 0x08): "qcaloric",      # Qundis qcaloric ısı sayacı
                }
                
                # Üretici ve tip ile eşleşen sürücüleri bul
                for (mfct, type_code), driver_name in driver_mapping.items():
                    if result["mfct"] == mfct and result["type"] == type_code:
                        result["suggested_drivers"].append(driver_name)
                        
                # Sadece üretici ile eşleşen sürücüleri bul
                mfct_mapping = {
                    "KAM": ["kamwater", "kamheat"],     # Kamstrup
                    "DME": ["hydrus", "izar"],          # Diehl
                    "LAS": ["lansenth", "lansenpu"],    # Lansen
                    "BMT": ["hydrodigit"],              # BMeters
                    "TCH": ["compact5", "vario451"],    # Techem
                    "APT": ["apator162"],               # Apator
                    "SON": ["supercom587"],             # Sontex
                    "ELV": ["ev200"],                   # Elvaco
                    "SEN": ["iperl"]                    # Sensus
                }
                
                if result["mfct"] in mfct_mapping and not result["suggested_drivers"]:
                    result["suggested_drivers"].extend(mfct_mapping[result["mfct"]])
                
                # Tipler için genel sürücüler
                type_mapping = {
                    0x02: ["electricity"],      # Elektrik
                    0x03: ["gas"],              # Gaz
                    0x04: ["heat"],             # Isı
                    0x07: ["water"],            # Su
                    0x08: ["heat_allocator"],   # Isı maliyet dağıtıcı
                    0x0D: ["heat_cooling"],     # Isı/soğutma
                    0x17: ["room_sensor"]       # Oda sensörü
                }
                
                if result["type"] in type_mapping and not result["suggested_drivers"]:
                    result["suggested_drivers"].extend(type_mapping[result["type"]])
                    
                # Hiç sürücü önerilemezse, auto sürücüsünü öner
                if not result["suggested_drivers"]:
                    result["suggested_drivers"].append("auto")
                
        except Exception as e:
            result["error"] = f"Telegram analiz hatası: {e}"
            
        return result


class MBusFrameType(IntEnum):
    """M-Bus çerçeve tipleri"""
    SINGLE_CHAR = 0
    SHORT = 1
    CONTROL = 2
    LONG = 3
    WMBUS_APL = 4  # Kablosuz M-Bus APL
    WMBUS_NWL = 5  # Kablosuz M-Bus NWL


class MBusFrame:
    """M-Bus çerçeve yapısı"""
    
    def __init__(self):
        """Çerçeve başlatma"""
        self.frame_type = MBusFrameType.LONG
        self.length = 0
        self.control = 0
        self.address = 0
        self.control_information = 0
        self.data = b''
        self.checksum = 0
        self.manufacturer = None
        self.identification = None
        self.version = None
        self.device_type = None
        
    @staticmethod
    def parse(data: bytes) -> Optional['MBusFrame']:
        """
        M-Bus çerçevesini ayrıştırır
        
        Args:
            data: Ayrıştırılacak veri
            
        Returns:
            Optional[MBusFrame]: Ayrıştırılan çerçeve veya None
        """
        if not data or len(data) < 1:
            return None
            
        # Çerçeve tipini belirle
        frame = MBusFrame()
        
        if len(data) == 1 and data[0] == 0xE5:
            # Tek karakterli çerçeve (ACK)
            frame.frame_type = MBusFrameType.SINGLE_CHAR
            return frame
            
        if len(data) < 5:
            # Çok kısa, geçersiz çerçeve
            return None
            
        # Başlangıç karakterini kontrol et
        if data[0] == 0x10:
            # Kısa çerçeve (MBUS)
            frame.frame_type = MBusFrameType.SHORT
            frame.control = data[1]
            frame.address = data[2]
            frame.checksum = data[3]
            
            # CRC kontrolü
            if not MBusProtocol.check_crc(data[:4]):
                logger.warning("Kısa çerçeve CRC hatası")
                return None
                
            return frame
            
        elif data[0] == 0x68:
            # Kontrol veya uzun çerçeve (MBUS)
            if len(data) < 9:
                # Çok kısa, geçersiz çerçeve
                return None
                
            # Uzunluğu kontrol et
            length1 = data[1]
            length2 = data[2]
            
            if length1 != length2:
                # Uzunluk eşleşmiyor, geçersiz çerçeve
                logger.warning(f"Çerçeve uzunluk eşleşmiyor: {length1} != {length2}")
                return None
                
            # İkinci başlangıç karakterini kontrol et
            if data[3] != 0x68:
                # Geçersiz çerçeve
                logger.warning("İkinci başlangıç karakteri geçersiz")
                return None
                
            # Uzunluk kontrolü
            if len(data) < length1 + 6:
                # Eksik veri
                logger.warning(f"Eksik veri: {len(data)} < {length1 + 6}")
                return None
                
            # Kontrol veya uzun çerçeve
            frame.length = length1
            frame.control = data[4]
            frame.address = data[5]
            frame.control_information = data[6]
            frame.data = data[7:7+length1-3]
            frame.checksum = data[7+length1-3]
            
            # Çerçeve tipini belirle
            if length1 == 3:
                # Kontrol çerçevesi
                frame.frame_type = MBusFrameType.CONTROL
            else:
                # Uzun çerçeve
                frame.frame_type = MBusFrameType.LONG
                
            # CRC kontrolü
            if not MBusProtocol.check_crc(data[4:7+length1-2]):
                logger.warning("Uzun çerçeve CRC hatası")
                return None
                
            return frame
            
        elif data[0] >= 0x44 and data[0] <= 0x4F:
            # Kablosuz M-Bus APL katmanı
            if len(data) < 10:
                return None
                
            frame.frame_type = MBusFrameType.WMBUS_APL
            
            # L-field
            frame.length = data[0]
            
            # C-field
            frame.control = data[1]
            
            # M-field (üretici kodu)
            manufacturer_code = (data[3] << 8) | data[2]
            frame.manufacturer = MBusProtocol.decode_manufacturer(manufacturer_code)
            
            # A-field (sayaç kimliği)
            id_bytes = data[4:8]
            frame.identification = ''.join(f'{b:02x}' for b in reversed(id_bytes))
            
            # Version
            frame.version = data[8]
            
            # Device type
            frame.device_type = data[9]
            
            # CI-field
            if len(data) > 10:
                frame.control_information = data[10]
                
            # Veri alanı
            if len(data) > 11:
                frame.data = data[11:]
                
            return frame
            
        return None
    
    def is_encrypted(self) -> bool:
        """
        Çerçevenin şifreli olup olmadığını kontrol eder
        
        Returns:
            bool: Şifreli mi?
        """
        if self.frame_type == MBusFrameType.WMBUS_APL:
            # Kablosuz M-Bus için şifreleme kontrolü
            return (self.control & 0x05) != 0
        return False
    
    def encode(self) -> bytes:
        """
        M-Bus çerçevesini kodlar
        
        Returns:
            bytes: Kodlanmış çerçeve
        """
        if self.frame_type == MBusFrameType.SINGLE_CHAR:
            # Tek karakterli çerçeve
            return bytes([0xE5])
            
        elif self.frame_type == MBusFrameType.SHORT:
            # Kısa çerçeve
            frame = bytes([0x10, self.control, self.address])
            # CRC hesapla
            crc = MBusProtocol.calculate_crc(frame)
            # Çerçeveyi tamamla
            return frame + bytes([crc, 0x16])
            
        elif self.frame_type == MBusFrameType.CONTROL:
            # Kontrol çerçevesi
            self.length = 3
            # Çerçeve başlık
            frame = bytes([0x68, self.length, self.length, 0x68])
            # Çerçeve içerik
            content = bytes([self.control, self.address, self.control_information])
            # CRC hesapla
            crc = MBusProtocol.calculate_crc(content)
            # Çerçeveyi tamamla
            return frame + content + bytes([crc, 0x16])
            
        elif self.frame_type == MBusFrameType.LONG:
            # Uzun çerçeve
            self.length = len(self.data) + 3
            # Çerçeve başlık
            frame = bytes([0x68, self.length, self.length, 0x68])
            # Çerçeve içerik
            content = bytes([self.control, self.address, self.control_information]) + self.data
            # CRC hesapla
            crc = MBusProtocol.calculate_crc(content)
            # Çerçeveyi tamamla
            return frame + content + bytes([crc, 0x16])
            
        elif self.frame_type == MBusFrameType.WMBUS_APL:
            # Kablosuz M-Bus APL katmanı
            # Bu kısım, kablosuz M-Bus formatına göre kodlama yapılmalı
            # Burada basitleştirilmiş bir versiyonu var
            
            # Gerekli alanlar kontrol edilmeli
            if not self.manufacturer or not self.identification or self.version is None or self.device_type is None:
                logger.error("Kablosuz M-Bus çerçevesi için gerekli alanlar eksik")
                return b''
                
            # Üretici kodunu çevir
            mfct_code = MBusProtocol.encode_manufacturer(self.manufacturer)
            
            # ID'yi byte dizisine dönüştür
            id_bytes = binascii.unhexlify(self.identification)
            if len(id_bytes) != 4:
                logger.error(f"Geçersiz ID uzunluğu: {len(id_bytes)}, 4 byte olmalı")
                return b''
                
            # ID'yi ters çevir (little endian)
            id_bytes = bytes(reversed(id_bytes))
            
            # Başlık uzunluğu + veri uzunluğu
            header_len = 11  # L + C + M + A + Ver + Type + CI
            self.length = header_len + len(self.data) - 1  # L-field kendisi hariç
            
            # Çerçeveyi oluştur
            frame = bytes([self.length, self.control])
            frame += mfct_code.to_bytes(2, byteorder='little')
            frame += id_bytes
            frame += bytes([self.version, self.device_type])
            
            # CI alanı ve veri
            if self.control_information is not None:
                frame += bytes([self.control_information])
                
            # Veriyi ekle
            if self.data:
                frame += self.data
                
            return frame
            
        return b''


class TelegramAccessPoint:
    """Telegram erişim noktası - Telegram akışını yönetir"""
    
    def __init__(self):
        """Erişim noktası başlatma"""
        self.meters = {}  # id -> meter
        self.last_telegrams = {}  # id -> telegram
        self.telegram_history = {}  # id -> [telegram, timestamp]
        self.telegram_queue = []
        self.max_history = 100  # Her sayaç için maksimum telegram geçmişi
        
    def add_meter(self, meter_id: str, meter_info: Dict[str, Any]) -> None:
        """
        Yeni bir sayaç ekler
        
        Args:
            meter_id: Sayaç kimliği
            meter_info: Sayaç bilgileri
        """
        self.meters[meter_id] = meter_info
        self.telegram_history[meter_id] = []
        
    def process_telegram(self, telegram_data: bytes) -> Optional[Dict[str, Any]]:
        """
        Telegram verisini işler
        
        Args:
            telegram_data: İşlenecek telegram verisi
            
        Returns:
            Optional[Dict[str, Any]]: İşleme sonucu veya None
        """
        # Analizci kullanarak telegram bilgilerini çıkar
        analysis = MBusProtocol.analyze_telegram(telegram_data)
        
        if not analysis["valid"]:
            logger.warning(f"Geçersiz telegram: {analysis.get('error', 'Bilinmeyen hata')}")
            return None
            
        # Telegram ID'si
        meter_id = analysis.get("id")
        if not meter_id:
            logger.warning("Telegram'da sayaç ID'si bulunamadı")
            return None
            
        # Son telegram'ı kaydet
        self.last_telegrams[meter_id] = {
            "data": telegram_data,
            "analysis": analysis,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        # Telegram geçmişine ekle
        if meter_id in self.telegram_history:
            # Geçmiş boyutu kontrol et
            if len(self.telegram_history[meter_id]) >= self.max_history:
                # En eski telegram'ı çıkar
                self.telegram_history[meter_id].pop(0)
                
            # Yeni telegram'ı ekle
            self.telegram_history[meter_id].append({
                "data": telegram_data.hex(),
                "timestamp": datetime.datetime.now().isoformat()
            })
            
        # İşleme sonucunu döndür
        return {
            "meter_id": meter_id,
            "manufacturer": analysis.get("mfct"),
            "type": analysis.get("type"),
            "type_name": analysis.get("type_name"),
            "version": analysis.get("version"),
            "encrypted": analysis.get("encrypted", False),
            "records": analysis.get("records", []),
            "suggested_drivers": analysis.get("suggested_drivers", [])
        }
        
    def get_telegram_history(self, meter_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Belirli bir sayaç için telegram geçmişini döndürür
        
        Args:
            meter_id: Sayaç kimliği
            limit: Döndürülecek maksimum telegram sayısı
            
        Returns:
            List[Dict[str, Any]]: Telegram geçmişi
        """
        if meter_id not in self.telegram_history:
            return []
            
        # En yeni telegraflar önce
        history = sorted(
            self.telegram_history[meter_id],
            key=lambda x: x["timestamp"],
            reverse=True
        )
        
        return history[:limit]
        
    def get_last_telegram(self, meter_id: str) -> Optional[Dict[str, Any]]:
        """
        Belirli bir sayaç için son telegram'ı döndürür
        
        Args:
            meter_id: Sayaç kimliği
            
        Returns:
            Optional[Dict[str, Any]]: Son telegram veya None
        """
        return self.last_telegrams.get(meter_id)
    
    def compare_telegrams(self, telegram1: bytes, telegram2: bytes) -> Dict[str, Any]:
        """
        İki telegramı karşılaştırır
        
        Args:
            telegram1: İlk telegram
            telegram2: İkinci telegram
            
        Returns:
            Dict[str, Any]: Karşılaştırma sonucu
        """
        # Her iki telegramı analiz et
        analysis1 = MBusProtocol.analyze_telegram(telegram1)
        analysis2 = MBusProtocol.analyze_telegram(telegram2)
        
        # Telegram ID'leri
        id1 = analysis1.get("id")
        id2 = analysis2.get("id")
        
        # İki telegram aynı sayaca ait mi?
        same_meter = id1 == id2
        
        # Kayıtları karşılaştır
        records1 = analysis1.get("records", [])
        records2 = analysis2.get("records", [])
        
        changed_records = []
        
        if same_meter and not analysis1.get("encrypted") and not analysis2.get("encrypted"):
            # Kayıtları karşılaştır
            for record1 in records1:
                for record2 in records2:
                    if record1["description"] == record2["description"] and \
                       record1["unit"] == record2["unit"] and \
                       record1["storage"] == record2["storage"] and \
                       record1["tariff"] == record2["tariff"]:
                        # Aynı alan, değerleri karşılaştır
                        if record1["value"] != record2["value"]:
                            changed_records.append({
                                "description": record1["description"],
                                "unit": record1["unit"],
                                "old_value": record1["value"],
                                "new_value": record2["value"],
                                "change": record2["value"] - record1["value"] if isinstance(record1["value"], (int, float)) and isinstance(record2["value"], (int, float)) else None
                            })
        
        return {
            "same_meter": same_meter,
            "meter_id": id1 if same_meter else f"{id1} vs {id2}",
            "changes": changed_records,
            "telegram1": {
                "encrypted": analysis1.get("encrypted", False),
                "records_count": len(records1)
            },
            "telegram2": {
                "encrypted": analysis2.get("encrypted", False),
                "records_count": len(records2)
            }
        }


class WMBusSecurity:
    """WMBus güvenlik işlemleri - şifreleme ve şifre çözme"""
    
    # OMS güvenlik modu
    SECURITY_NONE = 0
    SECURITY_CBC = 1
    SECURITY_CMAC = 2
    SECURITY_CMAC_AES = 5
    
    @staticmethod
    def decrypt_telegram(telegram_data: bytes, key: str, security_mode: int = SECURITY_CMAC) -> Optional[bytes]:
        """
        Şifreli bir telegramı çözer
        
        Args:
            telegram_data: Şifreli telegram verisi
            key: Şifreleme anahtarı (hex string)
            security_mode: Güvenlik modu
            
        Returns:
            Optional[bytes]: Çözülmüş telegram veya None
        """
        if not key:
            logger.error("Şifreleme anahtarı gerekli")
            return None
            
        try:
            # Telegram tipi kontrolü
            if len(telegram_data) < 11:
                logger.error("Telegram çok kısa")
                return None
                
            # Telegram başlık analizi
            analysis = MBusProtocol.analyze_telegram(telegram_data)
            
            if not analysis["valid"]:
                logger.error(f"Geçersiz telegram: {analysis.get('error', 'Bilinmeyen hata')}")
                return None
                
            # Şifreli değilse doğrudan döndür
            if not analysis.get("encrypted", False):
                logger.info("Telegram şifreli değil")
                return telegram_data
                
            # Üretici ve ID bilgileri
            manufacturer = analysis.get("mfct")
            meter_id = analysis.get("id")
            
            if not manufacturer or not meter_id:
                logger.error("Üretici veya sayaç ID'si bulunamadı")
                return None
                
            # Şifreli veri alanı
            encrypted_data = telegram_data[11:]
            
            # Güvenlik moduna göre şifre çözme
            if security_mode == WMBusSecurity.SECURITY_CBC:
                # AES-CBC şifre çözme
                decrypted_data = decrypt_aes_cbc(
                    encrypted_data, key, manufacturer, meter_id
                )
            elif security_mode == WMBusSecurity.SECURITY_CMAC or security_mode == WMBusSecurity.SECURITY_CMAC_AES:
                # AES-CMAC şifre çözme (MAC doğrulaması ile)
                decrypted_data, mac_verified = decrypt_aes_cmac(
                    encrypted_data, key, manufacturer, meter_id
                )
                
                if not mac_verified:
                    logger.warning("MAC doğrulama başarısız")
            else:
                logger.error(f"Desteklenmeyen güvenlik modu: {security_mode}")
                return None
                
            # Çözülmüş veriyi orijinal başlıkla birleştir
            decrypted_telegram = telegram_data[:11] + decrypted_data
            
            return decrypted_telegram
            
        except Exception as e:
            logger.error(f"Şifre çözme hatası: {e}")
            return None
    
    @staticmethod
    def generate_key(master_key: str, manufacturer: str, meter_id: str) -> str:
        """
        Belirli bir sayaç için şifreleme anahtarı üretir
        
        Args:
            master_key: Ana anahtar (hex string)
            manufacturer: Üretici kodu
            meter_id: Sayaç kimliği
            
        Returns:
            str: Üretilen anahtar (hex string)
        """
        try:
            # Master anahtarı kontrol et
            if not master_key or len(master_key.replace(" ", "")) != 32:
                logger.error("Geçersiz ana anahtar (32 hex karakter olmalı)")
                return ""
                
            # Master anahtarını ikili veriye dönüştür
            master_key_bytes = binascii.unhexlify(master_key.replace(" ", ""))
            
            # Türetme verisi için IV oluştur (cihaza özgü)
            iv = bytearray(16)
            
            # IV'ye üretici kodunu ekle
            for i, c in enumerate(manufacturer[:3]):
                if i < 3:
                    iv[i] = ord(c)
            
            # IV'ye sayaç kimliğini ekle
            try:
                id_bytes = binascii.unhexlify(meter_id)
                for i, b in enumerate(id_bytes[:8]):
                    if i < 8:
                        iv[i + 3] = b
            except binascii.Error:
                # ID hex değilse, karakter olarak işle
                for i, c in enumerate(meter_id[:8]):
                    if i < 8:
                        iv[i + 3] = ord(c)
            
            # Özel değişikliklere ayrılan alanları varsayılan değerlerde bırak
            # iv[11:] = bytes([0, 0, 0, 0, 0])
            
            # AES-ECB ile anahtar türetme
            if CRYPTO_AVAILABLE:
                cipher = AES.new(master_key_bytes, AES.MODE_ECB)
                derived_key = cipher.encrypt(bytes(iv))
                
                # Hex formatında döndür
                return derived_key.hex().upper()
            else:
                logger.error("PyCryptodome kütüphanesi bulunamadı")
                return ""
                
        except Exception as e:
            logger.error(f"Anahtar türetme hatası: {e}")
            return ""