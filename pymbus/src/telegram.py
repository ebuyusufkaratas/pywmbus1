"""
Telegram işleme ve ayrıştırma modülü
"""
import logging
import binascii
import struct
from typing import Dict, Optional, Tuple, List, Union
from .utils.encryption import decrypt_aes_cbc

logger = logging.getLogger(__name__)

class TelegramHeader:
    """Telegram başlık bilgilerini içeren sınıf"""
    
    def __init__(self, 
                 length: int = 0, 
                 control: int = 0, 
                 manufacturer: str = '', 
                 meter_id: str = '', 
                 version: int = 0, 
                 meter_type: int = 0):
        """
        Args:
            length: Telegram uzunluğu
            control: Kontrol alanı
            manufacturer: Üretici kodu
            meter_id: Sayaç kimliği
            version: Versiyon bilgisi
            meter_type: Sayaç tipi kodu
        """
        self.length = length
        self.control = control
        self.manufacturer = manufacturer
        self.meter_id = meter_id
        self.version = version
        self.meter_type = meter_type
        self.is_encrypted = bool(control & 0x05)  # Şifreleme biti kontrolü

    def __str__(self) -> str:
        return (f"TelegramHeader(mfct={self.manufacturer}, id={self.meter_id}, "
                f"ver=0x{self.version:02x}, type=0x{self.meter_type:02x}, "
                f"encrypted={self.is_encrypted})")

class Telegram:
    """M-Bus telegramı temsil eden sınıf"""
    
    def __init__(self, raw_data: Union[str, bytes]):
        """
        Args:
            raw_data: Ham telegram verisi (hex string veya bytes)
        """
        # Ham veriyi bytes'a dönüştür
        if isinstance(raw_data, str):
            try:
                self.raw_data = binascii.unhexlify(raw_data.replace(" ", ""))
            except binascii.Error as e:
                logger.error(f"Geçersiz hex string: {e}")
                self.raw_data = b''
        else:
            self.raw_data = raw_data
            
        self.header = None
        self.data_record = None
        self.parsed_data = {}
        
        if self.raw_data:
            self._parse_header()

    def _parse_header(self) -> None:
        """Telegram başlığını ayrıştırır"""
        if len(self.raw_data) < 10:
            logger.error(f"Telegram çok kısa: {len(self.raw_data)} bytes")
            return
            
        try:
            # L-field (tam uzunluk) alınır
            length = self.raw_data[0]
            
            # C-field (kontrol alanı)
            control = self.raw_data[1]
            
            # M-field (üretici kodu)
            m_field = struct.unpack("<H", self.raw_data[2:4])[0]
            # Üretici kodunu 3 karakterli koda dönüştür
            manufacturer = self._decode_manufacturer(m_field)
            
            # A-field (sayaç adresi)
            meter_id_bytes = self.raw_data[4:8]
            meter_id = ''.join(f'{b:02x}' for b in reversed(meter_id_bytes))
            
            # Version
            version = self.raw_data[8]
            
            # Device type
            meter_type = self.raw_data[9]
            
            self.header = TelegramHeader(
                length=length, 
                control=control, 
                manufacturer=manufacturer, 
                meter_id=meter_id, 
                version=version, 
                meter_type=meter_type
            )
            
            logger.debug(f"Telegram başlığı ayrıştırıldı: {self.header}")
            
        except (IndexError, struct.error) as e:
            logger.error(f"Telegram başlığı ayrıştırma hatası: {e}")
    
    def _decode_manufacturer(self, code: int) -> str:
        """
        Üretici kodunu 3 harfli koda dönüştürür
        
        Args:
            code: 16-bit üretici kodu
            
        Returns:
            str: 3 karakterli üretici kodu
        """
        # M-Bus protokolüne göre üretici kodu dönüşümü
        # Algoritma: https://www.m-bus.com/mbusdoc/md6.php
        char1 = ((code >> 10) & 0x1F) + 64
        char2 = ((code >> 5) & 0x1F) + 64
        char3 = (code & 0x1F) + 64
        return chr(char1) + chr(char2) + chr(char3)
    
    def decrypt(self, key: str) -> bool:
        """
        Şifreli telegram verisini çözer
        
        Args:
            key: AES şifreleme anahtarı (hex string)
            
        Returns:
            bool: Şifre çözme başarılı mı?
        """
        if not self.header or not self.header.is_encrypted:
            logger.debug("Telegram şifreli değil veya başlık ayrıştırılamadı")
            return True
            
        if not key:
            logger.error("Şifreli telegram için anahtar gerekli")
            return False
            
        try:
            # AES-CBC şifre çözme işlemi
            decrypted_data = decrypt_aes_cbc(
                self.raw_data[10:], 
                key, 
                self.header.manufacturer, 
                self.header.meter_id
            )
            
            # Çözülmüş veriyi telegram'a ekle
            self.raw_data = self.raw_data[:10] + decrypted_data
            logger.debug("Telegram şifresi çözüldü")
            return True
            
        except Exception as e:
            logger.error(f"Telegram şifre çözme hatası: {e}")
            return False
    
    def parse_data(self) -> Dict:
        """
        Telegram verisini ayrıştırır
        
        Returns:
            Dict: Ayrıştırılmış veri veya boş sözlük
        """
        if not self.header:
            return {}
            
        # Telegram verisini ayrıştırma (kullanıcı veri kayıtları)
        # Bu kısım protokol formatında daha detaylı kodlanmalıdır
        try:
            # Basit bir veri ayrıştırma örneği
            # Gerçek uygulamada ayrıntılı DIF/VIF ayrıştırması yapılmalıdır
            self.parsed_data = {
                "manufacturer": self.header.manufacturer,
                "meter_id": self.header.meter_id,
                "meter_type": self.header.meter_type,
                "version": self.header.version,
            }
            
            # CI alanı (veya diğer kontrol alanları)
            if len(self.raw_data) > 10:
                ci_field = self.raw_data[10]
                self.parsed_data["ci_field"] = ci_field
                
                # Veri alanını ayrıştır
                data_blocks = self._parse_data_blocks(self.raw_data[11:])
                if data_blocks:
                    self.parsed_data.update(data_blocks)
            
            return self.parsed_data
            
        except Exception as e:
            logger.error(f"Veri ayrıştırma hatası: {e}")
            return {}
    
    def _parse_data_blocks(self, data: bytes) -> Dict:
        """
        Veri bloklarını ayrıştırır
        
        Args:
            data: Ham veri bloğu
            
        Returns:
            Dict: Ayrıştırılmış veri blokları
        """
        blocks = {}
        
        # ... (mevcut kodun başı)
        
        pos = 0
        while pos < len(data):
            # En az 2 byte (DIF + VIF) veri gerekli
            if pos + 2 > len(data):
                break
                
            # DIF (Data Information Field)
            dif = data[pos]
            pos += 1
            
            # VIF (Value Information Field)
            vif = data[pos]
            pos += 1
            
            # Veri tipi ve uzunluğunu belirle
            data_type, length = self._get_data_type_and_length(dif)
            
            # Veri uzunluğunu kontrol et
            if pos + length > len(data):
                logger.warning(f"Veri bloğu eksik: {pos}+{length} > {len(data)}")
                # Kalan veriyi güvenli bir şekilde kullan veya atla
                # DÜZELTME: Veri bloğunu atla ve devam et
                break  # veya pos = len(data) ile döngüyü sonlandır
                
            # Veriyi çıkar
            value_bytes = data[pos:pos+length]
            pos += length
                
            # Veriyi çözümle
            value = self._decode_value(value_bytes, data_type)
            
            # Veri anlamını çözümle
            field_name, unit = self._get_field_info(vif)
            
            # Sonuca ekle
            if field_name:
                blocks[field_name] = value
                
                # Birim ekle
                if unit:
                    blocks[f"{field_name}_unit"] = unit
        
        return blocks
    
    def _get_data_type_and_length(self, dif: int) -> Tuple[str, int]:
        """
        DIF alanına göre veri tipi ve uzunluğunu belirler
        
        Args:
            dif: Data Information Field
            
        Returns:
            Tuple[str, int]: (veri tipi, uzunluk)
        """
        # DIF kodunu ayrıştır
        data_field = dif & 0x0F
        
        # Veri tipini belirle
        if data_field == 0x0:
            return "none", 0
        elif data_field == 0x1:
            return "int8", 1
        elif data_field == 0x2:
            return "int16", 2
        elif data_field == 0x3:
            return "int24", 3
        elif data_field == 0x4:
            return "int32", 4
        elif data_field == 0x5:
            return "float32", 4
        elif data_field == 0x6:
            return "int48", 6
        elif data_field == 0x7:
            return "int64", 8
        elif data_field == 0x9:
            return "bcd2", 2
        elif data_field == 0xA:
            return "bcd4", 4
        elif data_field == 0xB:
            return "bcd6", 6
        elif data_field == 0xC:
            return "bcd8", 8
        elif data_field == 0xD:
            return "variable", 0  # Değişken uzunluk
        elif data_field == 0xE:
            return "float64", 8
        else:
            return "unknown", 1
    
    def _decode_value(self, data: bytes, data_type: str) -> Union[int, float, str]:
        """
        Veri tipine göre değeri çözümler
        
        Args:
            data: Çözümlenecek veri
            data_type: Veri tipi
            
        Returns:
            Union[int, float, str]: Çözümlenmiş değer
        """
        try:
            if data_type == "none":
                return None
            elif data_type == "int8":
                return struct.unpack("B", data)[0]
            elif data_type == "int16":
                return struct.unpack("<H", data)[0]
            elif data_type == "int24":
                # 24-bit integer için özel işlem
                value = 0
                for i, b in enumerate(data):
                    value += b << (i * 8)
                return value
            elif data_type == "int32":
                return struct.unpack("<I", data)[0]
            elif data_type == "float32":
                return struct.unpack("<f", data)[0]
            elif data_type == "int48":
                # 48-bit integer için özel işlem
                value = 0
                for i, b in enumerate(data):
                    value += b << (i * 8)
                return value
            elif data_type == "int64":
                return struct.unpack("<Q", data)[0]
            elif data_type.startswith("bcd"):
                # BCD formatını çözümle
                result = 0
                for i, b in enumerate(data):
                    high = (b >> 4) & 0x0F
                    low = b & 0x0F
                    result += high * 10**(i*2+1) + low * 10**(i*2)
                return result
            elif data_type == "float64":
                return struct.unpack("<d", data)[0]
            elif data_type == "variable":
                # Değişken uzunluk, şu an için basit string olarak işle
                return data.hex()
            else:
                return data.hex()
        except Exception as e:
            logger.error(f"Değer çözümleme hatası ({data_type}): {e}")
            return data.hex()
    
    def _get_field_info(self, vif: int) -> Tuple[Optional[str], Optional[str]]:
        """
        VIF alanına göre alan adı ve birimini belirler
        
        Args:
            vif: Value Information Field
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (alan adı, birim)
        """
        # VIF kodunu ayrıştır
        value_type = vif & 0x7F
        
        # Alan adı ve birimini belirle (VIF tablosuna göre)
        if value_type >= 0x00 and value_type <= 0x07:
            # Enerji (Wh)
            multiplier = 10 ** (value_type - 3)
            return "energy", f"Wh * {multiplier}"
        elif value_type >= 0x08 and value_type <= 0x0F:
            # Enerji (J)
            multiplier = 10 ** (value_type - 3)
            return "energy", f"J * {multiplier}"
        elif value_type >= 0x10 and value_type <= 0x17:
            # Hacim (m3)
            multiplier = 10 ** (value_type - 6 - 3)
            return "volume", f"m3 * {multiplier}"
        elif value_type >= 0x18 and value_type <= 0x1F:
            # Kütle (kg)
            multiplier = 10 ** (value_type - 3)
            return "mass", f"kg * {multiplier}"
        elif value_type >= 0x20 and value_type <= 0x27:
            # Çalışma süresi
            multiplier = 10 ** (value_type - 0x20)
            return "on_time", f"s * {multiplier}"
        elif value_type >= 0x28 and value_type <= 0x2F:
            # Güç (W)
            multiplier = 10 ** (value_type - 0x28 - 3)
            return "power", f"W * {multiplier}"
        elif value_type >= 0x30 and value_type <= 0x37:
            # Güç (J/h)
            multiplier = 10 ** (value_type - 0x30 - 3)
            return "power", f"J/h * {multiplier}"
        elif value_type >= 0x38 and value_type <= 0x3F:
            # Hacim akışı (m3/h)
            multiplier = 10 ** (value_type - 0x38 - 6)
            return "volume_flow", f"m3/h * {multiplier}"
        elif value_type >= 0x40 and value_type <= 0x47:
            # Hacim akışı (m3/min)
            multiplier = 10 ** (value_type - 0x40 - 7)
            return "volume_flow", f"m3/min * {multiplier}"
        elif value_type >= 0x48 and value_type <= 0x4F:
            # Hacim akışı (m3/s)
            multiplier = 10 ** (value_type - 0x48 - 9)
            return "volume_flow", f"m3/s * {multiplier}"
        elif value_type >= 0x50 and value_type <= 0x57:
            # Kütle akışı (kg/h)
            multiplier = 10 ** (value_type - 0x50 - 3)
            return "mass_flow", f"kg/h * {multiplier}"
        elif value_type >= 0x58 and value_type <= 0x5B:
            # Akış sıcaklığı (°C)
            multiplier = 10 ** (value_type - 0x58 - 3)
            return "flow_temperature", f"°C * {multiplier}"
        elif value_type >= 0x5C and value_type <= 0x5F:
            # Dönüş sıcaklığı (°C)
            multiplier = 10 ** (value_type - 0x5C - 3)
            return "return_temperature", f"°C * {multiplier}"
        elif value_type >= 0x60 and value_type <= 0x63:
            # Sıcaklık farkı (K)
            multiplier = 10 ** (value_type - 0x60 - 3)
            return "temperature_difference", f"K * {multiplier}"
        elif value_type >= 0x64 and value_type <= 0x67:
            # Dış sıcaklık (°C)
            multiplier = 10 ** (value_type - 0x64 - 3)
            return "external_temperature", f"°C * {multiplier}"
        elif value_type >= 0x68 and value_type <= 0x6B:
            # Basınç (bar)
            multiplier = 10 ** (value_type - 0x68 - 3)
            return "pressure", f"bar * {multiplier}"
        elif value_type == 0x6C:
            # Tarih
            return "date", "date"
        elif value_type == 0x6D:
            # Zaman
            return "time", "time"
        elif value_type >= 0x70 and value_type <= 0x77:
            # Ortalama süre
            unit_map = {
                0x70: "s", 0x71: "min", 0x72: "h", 0x73: "day",
                0x74: "week", 0x75: "month", 0x76: "year", 0x77: "decade"
            }
            return "averaging_duration", unit_map.get(value_type, "unknown")
        elif value_type >= 0x78 and value_type <= 0x7F:
            # Aktüel süresi
            unit_map = {
                0x78: "s", 0x79: "min", 0x7A: "h", 0x7B: "day",
                0x7C: "week", 0x7D: "month", 0x7E: "year", 0x7F: "decade"
            }
            return "actuality_duration", unit_map.get(value_type, "unknown")
        else:
            # Bilinmeyen alan
            return f"unknown_{value_type:02x}", None

    def __str__(self) -> str:
        """İnsan okunabilir temsil"""
        if not self.header:
            return "Invalid Telegram"
            
        result = [f"Telegram from: {self.header.meter_id}"]
        result.append(f"Manufacturer: {self.header.manufacturer}")
        result.append(f"Type: 0x{self.header.meter_type:02x}")
        result.append(f"Version: 0x{self.header.version:02x}")
        result.append(f"Encrypted: {self.header.is_encrypted}")
        
        if self.parsed_data:
            result.append("Data:")
            for key, value in self.parsed_data.items():
                result.append(f"  {key}: {value}")
        
        return "\n".join(result)