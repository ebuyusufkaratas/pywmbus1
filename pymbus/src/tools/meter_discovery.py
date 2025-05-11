"""
Otomatik Sayaç Algılama ve Keşif Modülü

Bu modül, M-Bus/WMBus protokolünü kullanan sayaçları otomatik olarak
algılamak ve tanımlamak için kullanılır. Telegram analizini ve ağ
keşfini bir araya getirir.
"""

import binascii
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple

from pymbus.src.telegram import Telegram
from pymbus.src.protocol import MBusProtocol, DeviceType
from pymbus.src.drivers.auto import AutoDriver
from typing import Dict, List, Optional, Tuple, Union, Any, Set

# Log ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("meter_discovery")

class MeterInfo:
    """Sayaç bilgilerini tutan sınıf"""
    
    def __init__(self, meter_id: str, manufacturer: str = None, type_code: int = None):
        """
        Args:
            meter_id: Sayaç kimliği
            manufacturer: Üretici kodu
            type_code: Sayaç tipi kodu
        """
        self.meter_id = meter_id
        self.manufacturer = manufacturer
        self.type_code = type_code
        self.type_name = None
        self.version = None
        self.first_seen = datetime.now()
        self.last_seen = datetime.now()
        self.telegram_count = 0
        self.signal_strength = None  # RSSI değeri (dBm)
        self.recommended_driver = None
        self.data_records = []
        self.is_encrypted = False
        self.transmission_interval = None  # İletim aralığı (saniye)
        self.last_telegrams = []  # Son telegraflar (ham hex)
        self.last_values = {}  # Son okunan değerler
        
    def update_from_telegram(self, telegram_data: bytes, rssi: Optional[int] = None, 
                          driver: Optional[AutoDriver] = None) -> None:
        """
        Telegram verisinden sayaç bilgilerini günceller
        
        Args:
            telegram_data: Telegram verisi
            rssi: Sinyal gücü (dBm)
            driver: Otomatik sürücü nesnesi
        """
        # Telegram nesnesini oluştur
        telegram = Telegram(telegram_data)
        
        # Başlık geçerli mi?
        if not telegram.header:
            logger.warning(f"Geçersiz telegram başlığı: {telegram_data.hex()}")
            return
            
        # ID kontrolü
        if telegram.header.meter_id.lower() != self.meter_id.lower():
            logger.warning(f"Telegram sayaç ID uyumsuzluğu: {telegram.header.meter_id} != {self.meter_id}")
            return
            
        # Temel bilgileri güncelle
        self.manufacturer = telegram.header.manufacturer
        self.type_code = telegram.header.meter_type
        self.type_name = MBusProtocol.decode_device_type(telegram.header.meter_type)
        self.version = telegram.header.version
        self.is_encrypted = telegram.header.is_encrypted
        
        # İstatistikleri güncelle
        previous_time = self.last_seen
        self.last_seen = datetime.now()
        self.telegram_count += 1
        
        # Son iletim zamanı hesapla
        if self.telegram_count > 1:
            interval = (self.last_seen - previous_time).total_seconds()
            
            if self.transmission_interval is None:
                self.transmission_interval = interval
            else:
                # Hareketli ortalama
                self.transmission_interval = (self.transmission_interval * 0.8 + interval * 0.2)
        
        # Sinyal gücünü güncelle
        if rssi is not None:
            self.signal_strength = rssi
        
        # Son telegram'ı ekle
        telegram_hex = telegram_data.hex()
        self.last_telegrams.append({
            "data": telegram_hex,
            "timestamp": self.last_seen.isoformat()
        })
        
        # Maximum 5 telegram sakla
        if len(self.last_telegrams) > 5:
            self.last_telegrams.pop(0)
        
        # Şifreli değilse veri kayıtlarını ayrıştır
        if not self.is_encrypted:
            # Veri kayıtlarını ayrıştır
            records = MBusProtocol.parse_data_records(telegram.raw_data[10:])
            
            # Kayıtları sakla
            self.data_records = []
            for record in records:
                self.data_records.append({
                    "description": record.get_description(),
                    "value": record.parsed_value,
                    "unit": record.get_unit(),
                    "storage": record.storage_number,
                    "tariff": record.tariff,
                    "function": record.get_function_description()
                })
                
                # Son değerleri güncelle
                key = f"{record.get_description()}_{record.storage_number}_{record.tariff}"
                self.last_values[key] = {
                    "value": record.parsed_value,
                    "unit": record.get_unit(),
                    "updated": self.last_seen.isoformat()
                }
        
        # Sürücü önerisi
        if driver:
            self.recommended_driver = driver.find_driver(telegram)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Sayaç bilgilerini sözlük olarak döndürür
        
        Returns:
            Dict[str, Any]: Sayaç bilgileri
        """
        return {
            "meter_id": self.meter_id,
            "manufacturer": self.manufacturer,
            "type_code": self.type_code,
            "type_name": self.type_name,
            "version": f"0x{self.version:02x}" if self.version is not None else None,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "telegram_count": self.telegram_count,
            "signal_strength": self.signal_strength,
            "recommended_driver": self.recommended_driver,
            "data_records": self.data_records,
            "is_encrypted": self.is_encrypted,
            "transmission_interval": round(self.transmission_interval) if self.transmission_interval else None,
            "last_telegrams": self.last_telegrams[:3],  # Son 3 telegram
            "last_values": self.last_values
        }


class MeterDiscovery:
    """Sayaç keşif motoru"""
    
    def __init__(self):
        """Keşif motoru başlatma"""
        self.meters = {}  # meter_id -> MeterInfo
        self.auto_driver = AutoDriver()
        self.last_scan_time = None
        self.scan_results_dir = None  # Tarama sonuçlarının kaydedileceği dizin
        
    def process_telegram(self, telegram_data: Union[str, bytes], rssi: Optional[int] = None) -> Optional[str]:
        """
        Telegram verisini işler ve sayaç bilgilerini günceller
        
        Args:
            telegram_data: Telegram verisi (hex string veya bytes)
            rssi: Sinyal gücü (dBm)
            
        Returns:
            Optional[str]: İşlenen sayaç kimliği veya None
        """
        # Veriyi bytes'a dönüştür
        if isinstance(telegram_data, str):
            try:
                telegram_data = binascii.unhexlify(telegram_data.replace(" ", ""))
            except binascii.Error as e:
                logger.error(f"Geçersiz hex string: {e}")
                return None
        
        # Telegram nesnesini oluştur
        telegram = Telegram(telegram_data)
        
        # Başlık geçerli mi?
        if not telegram.header:
            logger.warning(f"Geçersiz telegram başlığı: {telegram_data.hex()}")
            return None
            
        # Sayaç ID'si
        meter_id = telegram.header.meter_id
        
        # Sayaç var mı kontrol et
        if meter_id not in self.meters:
            # Yeni sayaç
            logger.info(f"Yeni sayaç algılandı: {meter_id} ({telegram.header.manufacturer})")
            self.meters[meter_id] = MeterInfo(
                meter_id, 
                telegram.header.manufacturer,
                telegram.header.meter_type
            )
        
        # Sayaç bilgilerini güncelle
        self.meters[meter_id].update_from_telegram(telegram_data, rssi, self.auto_driver)
        
        return meter_id
    
    def get_meter(self, meter_id: str) -> Optional[MeterInfo]:
        """
        Belirli bir sayaç için bilgileri döndürür
        
        Args:
            meter_id: Sayaç kimliği
            
        Returns:
            Optional[MeterInfo]: Sayaç bilgileri veya None
        """
        return self.meters.get(meter_id)
    
    def get_meters(self) -> Dict[str, MeterInfo]:
        """
        Tüm sayaçları döndürür
        
        Returns:
            Dict[str, MeterInfo]: Sayaç bilgileri
        """
        return self.meters
    
    def get_meters_by_type(self, type_code: int) -> List[MeterInfo]:
        """
        Belirli bir tipteki tüm sayaçları döndürür
        
        Args:
            type_code: Sayaç tipi kodu
            
        Returns:
            List[MeterInfo]: Sayaç bilgileri listesi
        """
        return [meter for meter in self.meters.values() if meter.type_code == type_code]
    
    def get_meters_by_manufacturer(self, manufacturer: str) -> List[MeterInfo]:
        """
        Belirli bir üreticinin tüm sayaçlarını döndürür
        
        Args:
            manufacturer: Üretici kodu
            
        Returns:
            List[MeterInfo]: Sayaç bilgileri listesi
        """
        return [meter for meter in self.meters.values() if meter.manufacturer == manufacturer]
    
    def get_active_meters(self, max_age: int = 3600) -> List[MeterInfo]:
        """
        Aktif sayaçları döndürür
        
        Args:
            max_age: Maksimum yaş (saniye)
            
        Returns:
            List[MeterInfo]: Sayaç bilgileri listesi
        """
        now = datetime.now()
        max_age_delta = timedelta(seconds=max_age)
        
        return [meter for meter in self.meters.values() 
                if now - meter.last_seen < max_age_delta]
    
    def get_drivers_by_meter(self) -> Dict[str, List[str]]:
        """
        Sayaç tiplerine göre önerilen sürücüleri döndürür
        
        Returns:
            Dict[str, List[str]]: Sayaç tipi -> sürücü listesi
        """
        drivers_by_meter = defaultdict(set)
        
        for meter in self.meters.values():
            if meter.recommended_driver:
                type_name = meter.type_name or f"Unknown (0x{meter.type_code:02x})"
                drivers_by_meter[type_name].add(meter.recommended_driver)
        
        # Set'leri listelere dönüştür
        return {k: list(v) for k, v in drivers_by_meter.items()}
    
    def save_scan_results(self, directory: str) -> None:
        """
        Tarama sonuçlarını dosyaya kaydeder
        
        Args:
            directory: Kaydedilecek dizin
        """
        self.scan_results_dir = directory
        
        # Dizin var mı kontrol et
        if not os.path.exists(directory):
            os.makedirs(directory)
            
        # Sonuçları oluştur
        results = {
            "scan_time": datetime.now().isoformat(),
            "meter_count": len(self.meters),
            "meters": {meter_id: meter.to_dict() for meter_id, meter in self.meters.items()}
        }
        
        # Dosyaya kaydet
        filename = os.path.join(directory, f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        
        with open(filename, "w") as f:
            json.dump(results, f, indent=2)
            
        logger.info(f"Tarama sonuçları kaydedildi: {filename}")
        
        # En son tarama zamanını güncelle
        self.last_scan_time = datetime.now()
    
    def load_scan_results(self, filename: str) -> None:
        """
        Tarama sonuçlarını dosyadan yükler
        
        Args:
            filename: Dosya adı
        """
        try:
            with open(filename, "r") as f:
                results = json.load(f)
                
            # Sayaçları yükle
            meter_count = 0
            for meter_id, meter_data in results.get("meters", {}).items():
                # Yeni sayaç oluştur
                meter = MeterInfo(meter_id)
                
                # Temel bilgileri güncelle
                meter.manufacturer = meter_data.get("manufacturer")
                meter.type_code = meter_data.get("type_code")
                meter.type_name = meter_data.get("type_name")
                
                # Versiyon
                version_str = meter_data.get("version")
                if version_str and version_str.startswith("0x"):
                    meter.version = int(version_str[2:], 16)
                
                # Zaman bilgileri
                if "first_seen" in meter_data:
                    meter.first_seen = datetime.fromisoformat(meter_data["first_seen"])
                if "last_seen" in meter_data:
                    meter.last_seen = datetime.fromisoformat(meter_data["last_seen"])
                
                # Diğer bilgiler
                meter.telegram_count = meter_data.get("telegram_count", 0)
                meter.signal_strength = meter_data.get("signal_strength")
                meter.recommended_driver = meter_data.get("recommended_driver")
                meter.data_records = meter_data.get("data_records", [])
                meter.is_encrypted = meter_data.get("is_encrypted", False)
                meter.transmission_interval = meter_data.get("transmission_interval")
                meter.last_telegrams = meter_data.get("last_telegrams", [])
                meter.last_values = meter_data.get("last_values", {})
                
                # Sayacı ekle
                self.meters[meter_id] = meter
                meter_count += 1
                
            logger.info(f"Tarama sonuçları yüklendi: {filename}, {meter_count} sayaç")
            
            # Tarama zamanını güncelle
            scan_time = results.get("scan_time")
            if scan_time:
                self.last_scan_time = datetime.fromisoformat(scan_time)
                
        except Exception as e:
            logger.error(f"Tarama sonuçları yüklenirken hata: {e}")
    
    def analyze_telegram_patterns(self) -> Dict[str, Any]:
        """
        Telegram iletim örüntülerini analiz eder
        
        Returns:
            Dict[str, Any]: Analiz sonuçları
        """
        results = {
            "total_meters": len(self.meters),
            "manufacturer_stats": defaultdict(int),
            "type_stats": defaultdict(int),
            "transmission_intervals": {},
            "encrypted_count": 0
        }
        
        # Tüm sayaçları analiz et
        for meter in self.meters.values():
            # Üretici istatistikleri
            if meter.manufacturer:
                results["manufacturer_stats"][meter.manufacturer] += 1
                
            # Tip istatistikleri
            if meter.type_name:
                results["type_stats"][meter.type_name] += 1
                
            # İletim aralığı
            if meter.transmission_interval:
                interval = round(meter.transmission_interval)
                if interval not in results["transmission_intervals"]:
                    results["transmission_intervals"][interval] = 0
                results["transmission_intervals"][interval] += 1
                
            # Şifreleme istatistikleri
            if meter.is_encrypted:
                results["encrypted_count"] += 1
        
        # İstatistikleri yüzdeye dönüştür
        if results["total_meters"] > 0:
            results["encrypted_percentage"] = round(results["encrypted_count"] / results["total_meters"] * 100)
        else:
            results["encrypted_percentage"] = 0
            
        return results
    
    def generate_configuration(self, output_file: str = None) -> Dict[str, Any]:
        """
        Sayaç yapılandırma dosyaları oluşturur
        
        Args:
            output_file: Çıktı dosyası (isteğe bağlı)
            
        Returns:
            Dict[str, Any]: Oluşturulan yapılandırma
        """
        config = {
            "generated_time": datetime.now().isoformat(),
            "meters": []
        }
        
        # Tüm sayaçlar için yapılandırma oluştur
        for meter_id, meter in self.meters.items():
            # Temel sayaç bilgileri
            meter_config = {
                "name": f"Meter_{meter_id[-8:]}",  # Son 8 karakterden isim oluştur
                "id": meter_id,
                "driver": meter.recommended_driver or "auto",
                "key": "" if meter.is_encrypted else "NOKEY"
            }
            
            # Tip bilgisine göre isim düzenle
            if meter.type_name:
                if "water" in meter.type_name.lower():
                    meter_config["name"] = f"Water_{meter_id[-8:]}"
                elif "heat" in meter.type_name.lower():
                    meter_config["name"] = f"Heat_{meter_id[-8:]}"
                elif "electricity" in meter.type_name.lower():
                    meter_config["name"] = f"Electricity_{meter_id[-8:]}"
                elif "gas" in meter.type_name.lower():
                    meter_config["name"] = f"Gas_{meter_id[-8:]}"
            
            # Yapılandırmaya ekle
            config["meters"].append(meter_config)
        
        # Dosyaya kaydet
        if output_file:
            with open(output_file, "w") as f:
                json.dump(config, f, indent=2)
                
            logger.info(f"Yapılandırma dosyası oluşturuldu: {output_file}")
            
        return config
    
    def print_meter_summary(self) -> None:
        """Algılanan sayaçların özetini yazdırır"""
        if not self.meters:
            print("Algılanan sayaç yok.")
            return
            
        print(f"Toplam {len(self.meters)} sayaç algılandı:")
        print("-" * 80)
        print(f"{'ID':12} {'Üretici':6} {'Tip':20} {'Şifreli':8} {'İletim Aralığı':16} {'Son Görülme':20}")
        print("-" * 80)
        
        for meter_id, meter in sorted(self.meters.items()):
            encrypted = "Evet" if meter.is_encrypted else "Hayır"
            interval = f"{round(meter.transmission_interval)} s" if meter.transmission_interval else "?"
            last_seen = meter.last_seen.strftime("%Y-%m-%d %H:%M:%S")
            
            type_name = meter.type_name or f"Unknown (0x{meter.type_code:02x})" if meter.type_code is not None else "?"
            
            # Kısa bilgiler
            print(f"{meter_id[-12:]:12} {meter.manufacturer or '?':6} {type_name[:20]:20} {encrypted:8} {interval:16} {last_seen:20}")
        
        print("-" * 80)
        
        # İstatistikler
        patterns = self.analyze_telegram_patterns()
        print(f"\nŞifreli sayaçlar: {patterns['encrypted_count']} ({patterns['encrypted_percentage']}%)")
        
        # Üretici istatistikleri
        if patterns["manufacturer_stats"]:
            print("\nÜretici dağılımı:")
            for mfct, count in sorted(patterns["manufacturer_stats"].items(), key=lambda x: x[1], reverse=True):
                print(f"  {mfct}: {count} sayaç")
                
        # Tip istatistikleri
        if patterns["type_stats"]:
            print("\nSayaç tipi dağılımı:")
            for type_name, count in sorted(patterns["type_stats"].items(), key=lambda x: x[1], reverse=True):
                print(f"  {type_name}: {count} sayaç")
                
        # İletim aralığı istatistikleri
        if patterns["transmission_intervals"]:
            print("\nİletim aralığı dağılımı:")
            for interval, count in sorted(patterns["transmission_intervals"].items()):
                print(f"  {interval} saniye: {count} sayaç")


class KeyDiscovery:
    """
    Şifreleme anahtarı keşif sistemi
    
    NOT: Bu sınıf, gerçek anahtar kırma işlemi için kullanılmaz!
    Sadece bilinen anahtarları yönetmek ve sayaçlara eşleştirmek için kullanılır.
    """
    
    def __init__(self):
        """Anahtar keşif sistemi başlatma"""
        self.known_keys = {}  # Bilinen anahtarlar
        self.meter_keys = {}  # Sayaç -> anahtar
        self.key_matches = {}  # Anahtar -> [sayaç]
        
    def add_key(self, key: str, description: str = None, manufacturer: str = None) -> bool:
        """
        Bilinen bir anahtar ekler
        
        Args:
            key: Şifreleme anahtarı (hex)
            description: Anahtar açıklaması
            manufacturer: İlişkili üretici (isteğe bağlı)
            
        Returns:
            bool: Ekleme başarılı mı?
        """
        # Anahtar formatını doğrula
        key = key.replace(" ", "").upper()
        if not all(c in "0123456789ABCDEF" for c in key):
            logger.error(f"Geçersiz anahtar format: {key}")
            return False
            
        # Uzunluk kontrolü (16 byte)
        if len(key) != 32:
            logger.error(f"Geçersiz anahtar uzunluğu: {len(key)}, 32 hex karakter olmalı")
            return False
            
        # Anahtarı ekle
        self.known_keys[key] = {
            "description": description,
            "manufacturer": manufacturer,
            "added": datetime.now().isoformat()
        }
        
        return True
    
    def match_key_to_meter(self, meter_id: str, key: str) -> None:
        """
        Bir anahtarı bir sayaç ile eşleştirir
        
        Args:
            meter_id: Sayaç kimliği
            key: Şifreleme anahtarı
        """
        key = key.replace(" ", "").upper()
        
        # Sayaç -> anahtar eşleştirmesi
        self.meter_keys[meter_id] = key
        
        # Anahtar -> sayaç eşleştirmesi
        if key not in self.key_matches:
            self.key_matches[key] = []
            
        if meter_id not in self.key_matches[key]:
            self.key_matches[key].append(meter_id)
    
    def get_keys_for_manufacturer(self, manufacturer: str) -> List[str]:
        """
        Belirli bir üretici için bilinen anahtarları döndürür
        
        Args:
            manufacturer: Üretici kodu
            
        Returns:
            List[str]: Anahtarlar listesi
        """
        return [
            key for key, info in self.known_keys.items() 
            if info.get("manufacturer") == manufacturer
        ]
    
    def get_key_for_meter(self, meter_id: str) -> Optional[str]:
        """
        Belirli bir sayaç için eşleşen anahtarı döndürür
        
        Args:
            meter_id: Sayaç kimliği
            
        Returns:
            Optional[str]: Anahtar veya None
        """
        return self.meter_keys.get(meter_id)
    
    def save_keys(self, filename: str) -> None:
        """
        Anahtarları dosyaya kaydeder
        
        Args:
            filename: Dosya adı
        """
        data = {
            "known_keys": self.known_keys,
            "meter_keys": self.meter_keys,
            "saved_time": datetime.now().isoformat()
        }
        
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
            
        logger.info(f"Anahtarlar kaydedildi: {filename}")
    
    def load_keys(self, filename: str) -> None:
        """
        Anahtarları dosyadan yükler
        
        Args:
            filename: Dosya adı
        """
        try:
            with open(filename, "r") as f:
                data = json.load(f)
                
            self.known_keys = data.get("known_keys", {})
            self.meter_keys = data.get("meter_keys", {})
            
            # Anahtar -> sayaç eşleştirmelerini yeniden oluştur
            self.key_matches = {}
            for meter_id, key in self.meter_keys.items():
                if key not in self.key_matches:
                    self.key_matches[key] = []
                    
                if meter_id not in self.key_matches[key]:
                    self.key_matches[key].append(meter_id)
            
            logger.info(f"Anahtarlar yüklendi: {filename}")
            
        except Exception as e:
            logger.error(f"Anahtarlar yüklenirken hata: {e}")
    
    def print_keys(self) -> None:
        """Bilinen anahtarları yazdırır"""
        if not self.known_keys:
            print("Bilinen anahtar yok.")
            return
            
        print(f"Toplam {len(self.known_keys)} bilinen anahtar:")
        print("-" * 80)
        for key, info in sorted(self.known_keys.items()):
            description = info.get("description") or "?"
            manufacturer = info.get("manufacturer") or "?"
            meter_count = len(self.key_matches.get(key, []))
            
            print(f"{key[:8]}...{key[-8:]} | {manufacturer:6} | {description[:30]:30} | {meter_count} sayaç")
        
        print("-" * 80)


def main():
    """Sayaç keşif modülü ana fonksiyonu"""
    import argparse
    
    # Argüman ayrıştırıcı
    parser = argparse.ArgumentParser(description="WMBus Sayaç Keşif Aracı")
    
    # Alt komutlar
    subparsers = parser.add_subparsers(dest="command", help="Komut")
    
    # Telegram işleme komutu
    process_parser = subparsers.add_parser("process", help="Telegram işleme")
    process_parser.add_argument("telegram", help="İşlenecek telegram hex string")
    process_parser.add_argument("--rssi", type=int, help="Sinyal gücü (dBm)")
    
    # Tarama komutu
    scan_parser = subparsers.add_parser("scan", help="Sayaç taraması")
    scan_parser.add_argument("--file", help="Taranacak telegram dosyası")
    scan_parser.add_argument("--output", help="Tarama sonuçlarının kaydedileceği dizin")
    scan_parser.add_argument("--interval", type=float, default=1.0, help="Tarama aralığı (saniye)")
    scan_parser.add_argument("--duration", type=int, default=60, help="Tarama süresi (saniye)")
    
    # Yapılandırma oluşturma komutu
    config_parser = subparsers.add_parser("config", help="Yapılandırma oluşturma")
    config_parser.add_argument("--scan", help="Tarama sonuçları dosyası")
    config_parser.add_argument("--output", help="Oluşturulacak yapılandırma dosyası")
    
    # Anahtar yönetimi komutu
    keys_parser = subparsers.add_parser("keys", help="Anahtar yönetimi")
    keys_parser.add_argument("--add", help="Eklenecek anahtar")
    keys_parser.add_argument("--description", help="Anahtar açıklaması")
    keys_parser.add_argument("--manufacturer", help="İlişkili üretici")
    keys_parser.add_argument("--file", help="Anahtar dosyası")
    keys_parser.add_argument("--save", help="Anahtarları kaydetme dosyası")
    
    # Argümanları ayrıştır
    args = parser.parse_args()
    
    # Keşif nesnesi oluştur
    discovery = MeterDiscovery()
    
    # Komuta göre işlem yap
    if args.command == "process":
        # Telegram işleme
        meter_id = discovery.process_telegram(args.telegram, args.rssi)
        
        if meter_id:
            meter = discovery.get_meter(meter_id)
            print(f"İşlenen sayaç: {meter_id}")
            print(f"Üretici: {meter.manufacturer}")
            print(f"Tip: {meter.type_name}")
            print(f"Şifreli: {'Evet' if meter.is_encrypted else 'Hayır'}")
            
            if meter.data_records:
                print("\nVeri kayıtları:")
                for i, record in enumerate(meter.data_records):
                    print(f"{i+1}. {record['description']}: {record['value']} {record['unit']}")
        else:
            print("Telegram işlenirken hata oluştu.")
    
    elif args.command == "scan":
        # Sayaç taraması
        if args.file:
            print(f"Dosya taranıyor: {args.file}")
            
            # Dosyayı oku
            try:
                with open(args.file, "r") as f:
                    lines = f.readlines()
                    
                for line in lines:
                    # Yorum satırlarını atla
                    if line.strip().startswith("#"):
                        continue
                        
                    # Boş satırları atla
                    if not line.strip():
                        continue
                        
                    # Telegram'ı işle
                    discovery.process_telegram(line.strip())
                    
                # Tarama sonuçlarını göster
                discovery.print_meter_summary()
                
                # Tarama sonuçlarını kaydet
                if args.output:
                    discovery.save_scan_results(args.output)
                    
            except Exception as e:
                print(f"Dosya tarama hatası: {e}")
                
        else:
            print("Tarama için bir dosya belirtilmedi.")
    
    elif args.command == "config":
        # Yapılandırma oluşturma
        if args.scan:
            # Tarama sonuçlarını yükle
            discovery.load_scan_results(args.scan)
            
        # Sayaç yoksa uyarı ver
        if not discovery.meters:
            print("Yapılandırma oluşturmak için sayaç bulunamadı.")
            return
            
        # Yapılandırma oluştur
        config = discovery.generate_configuration(args.output)
        
        # Sonuçları göster
        print(f"Toplam {len(config['meters'])} sayaç için yapılandırma oluşturuldu.")
        
        if args.output:
            print(f"Yapılandırma dosyası oluşturuldu: {args.output}")
            
    elif args.command == "keys":
        # Anahtar yönetimi
        key_discovery = KeyDiscovery()
        
        # Anahtar dosyasını yükle
        if args.file:
            key_discovery.load_keys(args.file)
            
        # Anahtar ekle
        if args.add:
            success = key_discovery.add_key(
                args.add,
                args.description,
                args.manufacturer
            )
            
            if success:
                print(f"Anahtar eklendi: {args.add}")
                
                # Anahtarları kaydet
                if args.save:
                    key_discovery.save_keys(args.save)
            else:
                print(f"Anahtar eklenirken hata oluştu: {args.add}")
        
        # Anahtarları görüntüle
        key_discovery.print_keys()
        
    else:
        parser.print_help()

if __name__ == "__main__":
    main()