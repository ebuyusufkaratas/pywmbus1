"""
Telegram Analiz ve Debug Aracı

Bu modül, M-Bus/WMBus telegramlarını analiz etmek, görselleştirmek ve
debug etmek için kullanılır. Hem komut satırı arayüzü hem de işlevsel
API sunar.
"""

import argparse
import binascii
import colorama
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Union

# Renkli konsol çıktısı için Colorama'yı başlat
colorama.init()

# Pymbus modüllerini import et
from pymbus.src.telegram import Telegram
from pymbus.src.protocol import MBusProtocol, MBusDataRecord, DeviceType
from pymbus.src.drivers.auto import AutoDriver

# Log ayarları
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("telegram_analyzer")

class TelegramAnalyzer:
    """Telegram analiz motoru"""
    
    def __init__(self):
        """Analizci başlatma"""
        self.auto_driver = AutoDriver()
        
    def analyze_telegram(self, telegram_hex: str) -> Dict[str, Any]:
        """
        Telegram'ı analiz eder ve detaylı bilgiler çıkarır
        
        Args:
            telegram_hex: Analiz edilecek telegram hex string
            
        Returns:
            Dict[str, Any]: Analiz sonuçları
        """
        # Hex string kontrolü
        try:
            # Boşlukları temizle ve hex'e dönüştür
            telegram_data = binascii.unhexlify(telegram_hex.replace(" ", ""))
        except binascii.Error as e:
            return {"error": f"Geçersiz hex string: {e}"}
            
        # Telegram nesnesini oluştur
        telegram = Telegram(telegram_data)
        
        # Başlık kontrolü
        if not telegram.header:
            return {"error": "Telegram başlığı ayrıştırılamadı"}
            
        # Tam protokol analizini çağır
        analysis = MBusProtocol.analyze_telegram(telegram_data)
        
        # Sürücü önerisi al
        driver_name = self.auto_driver.find_driver(telegram)
        
        # Analiz sonuçlarına sürücü ekle
        if driver_name:
            analysis["recommended_driver"] = driver_name
            
        return analysis
    
    def decrypt_telegram(self, telegram_hex: str, key: str) -> Dict[str, Any]:
        """
        Şifreli telegram'ı çözer
        
        Args:
            telegram_hex: Şifreli telegram hex string
            key: Şifreleme anahtarı
            
        Returns:
            Dict[str, Any]: Şifre çözme sonuçları
        """
        # Hex string kontrolü
        try:
            # Boşlukları temizle ve hex'e dönüştür
            telegram_data = binascii.unhexlify(telegram_hex.replace(" ", ""))
        except binascii.Error as e:
            return {"error": f"Geçersiz hex string: {e}"}
            
        # Telegram nesnesini oluştur
        telegram = Telegram(telegram_data)
        
        # Başlık kontrolü
        if not telegram.header:
            return {"error": "Telegram başlığı ayrıştırılamadı"}
            
        # Şifreleme kontrolü
        if not telegram.header.is_encrypted:
            return {
                "status": "unencrypted",
                "message": "Telegram zaten şifreli değil",
                "telegram": telegram_hex
            }
            
        # Şifre çöz
        if telegram.decrypt(key):
            # Şifre çözme başarılı
            return {
                "status": "success",
                "message": "Şifre çözme başarılı",
                "telegram": telegram.raw_data.hex(),
                "records": self._extract_records(telegram)
            }
        else:
            # Şifre çözme başarısız
            return {
                "status": "failed",
                "message": "Şifre çözme başarısız",
                "telegram": telegram_hex
            }
    
    def compare_telegrams(self, telegram1_hex: str, telegram2_hex: str) -> Dict[str, Any]:
        """
        İki telegram'ı karşılaştırır
        
        Args:
            telegram1_hex: İlk telegram hex string
            telegram2_hex: İkinci telegram hex string
            
        Returns:
            Dict[str, Any]: Karşılaştırma sonuçları
        """
        # Hex string kontrolü
        try:
            # Boşlukları temizle ve hex'e dönüştür
            telegram1_data = binascii.unhexlify(telegram1_hex.replace(" ", ""))
            telegram2_data = binascii.unhexlify(telegram2_hex.replace(" ", ""))
        except binascii.Error as e:
            return {"error": f"Geçersiz hex string: {e}"}
            
        # Telegram nesnelerini oluştur
        telegram1 = Telegram(telegram1_data)
        telegram2 = Telegram(telegram2_data)
        
        # Başlık kontrolü
        if not telegram1.header:
            return {"error": "İlk telegram başlığı ayrıştırılamadı"}
            
        if not telegram2.header:
            return {"error": "İkinci telegram başlığı ayrıştırılamadı"}
            
        # Karşılaştırma sonuçları
        result = {
            "header_comparison": self._compare_headers(telegram1, telegram2),
            "data_comparison": self._compare_data(telegram1, telegram2)
        }
        
        return result
    
    def _compare_headers(self, telegram1: Telegram, telegram2: Telegram) -> Dict[str, Any]:
        """
        İki telegram başlığını karşılaştırır
        
        Args:
            telegram1: İlk telegram
            telegram2: İkinci telegram
            
        Returns:
            Dict[str, Any]: Karşılaştırma sonuçları
        """
        header1 = telegram1.header
        header2 = telegram2.header
        
        # Tüm alanları karşılaştır
        diffs = {}
        
        # Üretici
        if header1.manufacturer != header2.manufacturer:
            diffs["manufacturer"] = {
                "telegram1": header1.manufacturer,
                "telegram2": header2.manufacturer
            }
            
        # Sayaç ID
        if header1.meter_id != header2.meter_id:
            diffs["meter_id"] = {
                "telegram1": header1.meter_id,
                "telegram2": header2.meter_id
            }
            
        # Versiyon
        if header1.version != header2.version:
            diffs["version"] = {
                "telegram1": f"0x{header1.version:02x}",
                "telegram2": f"0x{header2.version:02x}"
            }
            
        # Tip
        if header1.meter_type != header2.meter_type:
            diffs["meter_type"] = {
                "telegram1": f"0x{header1.meter_type:02x}",
                "telegram2": f"0x{header2.meter_type:02x}"
            }
            
        # Şifreleme durumu
        if header1.is_encrypted != header2.is_encrypted:
            diffs["encrypted"] = {
                "telegram1": header1.is_encrypted,
                "telegram2": header2.is_encrypted
            }
            
        # Sonuç
        return {
            "same_meter": header1.meter_id == header2.meter_id,
            "same_headers": len(diffs) == 0,
            "differences": diffs
        }
    
    def _compare_data(self, telegram1: Telegram, telegram2: Telegram) -> Dict[str, Any]:
        """
        İki telegram'ın veri alanlarını karşılaştırır
        
        Args:
            telegram1: İlk telegram
            telegram2: İkinci telegram
            
        Returns:
            Dict[str, Any]: Karşılaştırma sonuçları
        """
        # Şifreli mi kontrol et
        if telegram1.header.is_encrypted or telegram2.header.is_encrypted:
            return {
                "message": "Şifreli telegramlar karşılaştırılamaz",
                "can_compare": False
            }
            
        # Veri kayıtlarını çıkar
        records1 = self._extract_records(telegram1)
        records2 = self._extract_records(telegram2)
        
        # Alanları karşılaştır
        same_fields = []
        different_fields = []
        only_in_first = []
        only_in_second = []
        
        # İlk telegram'ın alanlarını kontrol et
        for record1 in records1:
            found = False
            
            for record2 in records2:
                # Aynı alansa
                if record1["description"] == record2["description"] and \
                   record1["unit"] == record2["unit"] and \
                   record1["storage"] == record2["storage"] and \
                   record1["tariff"] == record2["tariff"]:
                    found = True
                    
                    # Değerleri karşılaştır
                    if record1["value"] == record2["value"]:
                        same_fields.append({
                            "description": record1["description"],
                            "value": record1["value"],
                            "unit": record1["unit"]
                        })
                    else:
                        # Değer farklı
                        diff = None
                        if isinstance(record1["value"], (int, float)) and isinstance(record2["value"], (int, float)):
                            diff = record2["value"] - record1["value"]
                            
                        different_fields.append({
                            "description": record1["description"],
                            "value1": record1["value"],
                            "value2": record2["value"],
                            "unit": record1["unit"],
                            "diff": diff
                        })
                    
                    break
            
            # İkinci telegram'da bulunamadı
            if not found:
                only_in_first.append({
                    "description": record1["description"],
                    "value": record1["value"],
                    "unit": record1["unit"]
                })
                
        # İkinci telegram'da olup ilk telegram'da olmayan alanlar
        for record2 in records2:
            found = False
            
            for record1 in records1:
                # Aynı alansa
                if record1["description"] == record2["description"] and \
                   record1["unit"] == record2["unit"] and \
                   record1["storage"] == record2["storage"] and \
                   record1["tariff"] == record2["tariff"]:
                    found = True
                    break
            
            # İlk telegram'da bulunamadı
            if not found:
                only_in_second.append({
                    "description": record2["description"],
                    "value": record2["value"],
                    "unit": record2["unit"]
                })
                
        # Sonuç
        return {
            "can_compare": True,
            "same_fields_count": len(same_fields),
            "different_fields_count": len(different_fields),
            "only_in_first_count": len(only_in_first),
            "only_in_second_count": len(only_in_second),
            "same_fields": same_fields,
            "different_fields": different_fields,
            "only_in_first": only_in_first,
            "only_in_second": only_in_second
        }
    
    def _extract_records(self, telegram: Telegram) -> List[Dict[str, Any]]:
        """
        Telegram'dan veri kayıtlarını çıkarır
        
        Args:
            telegram: Telegram nesnesi
            
        Returns:
            List[Dict[str, Any]]: Veri kayıtları
        """
        # Başlık kontrolü
        if not telegram.header:
            return []
            
        # Veri alanındaki kayıtları ayrıştır
        data_records = MBusProtocol.parse_data_records(telegram.raw_data[10:])
        
        # Sonuç listesi
        records = []
        
        # Kayıtları dönüştür
        for record in data_records:
            records.append({
                "description": record.get_description(),
                "value": record.parsed_value,
                "unit": record.get_unit(),
                "storage": record.storage_number,
                "tariff": record.tariff,
                "function": record.get_function_description()
            })
            
        return records
    
    def print_telegram_analysis(self, analysis: Dict[str, Any], color: bool = True) -> None:
        """
        Telegram analiz sonuçlarını konsola yazdırır
        
        Args:
            analysis: Analiz sonuçları
            color: Renkli çıktı kullanılsın mı?
        """
        # Hata kontrolü
        if "error" in analysis:
            if color:
                print(f"{colorama.Fore.RED}HATA: {analysis['error']}{colorama.Style.RESET_ALL}")
            else:
                print(f"HATA: {analysis['error']}")
            return
            
        # Geçerlilik kontrolü
        if not analysis.get("valid", False):
            if color:
                print(f"{colorama.Fore.RED}Geçersiz telegram!{colorama.Style.RESET_ALL}")
            else:
                print("Geçersiz telegram!")
            return
            
        # Başlık bilgileri
        if color:
            print(f"{colorama.Fore.GREEN}=== Telegram Başlığı ==={colorama.Style.RESET_ALL}")
        else:
            print("=== Telegram Başlığı ===")
            
        print(f"Üretici: {analysis.get('mfct', 'Bilinmiyor')}")
        print(f"Sayaç ID: {analysis.get('id', 'Bilinmiyor')}")
        print(f"Cihaz tipi: {analysis.get('type_name', 'Bilinmiyor')} (0x{analysis.get('type', 0):02x})")
        print(f"Versiyon: 0x{analysis.get('version', 0):02x}")
        print(f"Şifreli: {'Evet' if analysis.get('encrypted', False) else 'Hayır'}")
        
        # CI alanı
        if "ci_field" in analysis:
            print(f"CI alanı: 0x{analysis['ci_field']:02x}")
            
        # Önerilen sürücüler
        if "suggested_drivers" in analysis:
            if color:
                print(f"\n{colorama.Fore.CYAN}Önerilen sürücüler:{colorama.Style.RESET_ALL} {', '.join(analysis['suggested_drivers'])}")
            else:
                print(f"\nÖnerilen sürücüler: {', '.join(analysis['suggested_drivers'])}")
                
        if "recommended_driver" in analysis:
            if color:
                print(f"{colorama.Fore.GREEN}Tavsiye edilen sürücü:{colorama.Style.RESET_ALL} {analysis['recommended_driver']}")
            else:
                print(f"Tavsiye edilen sürücü: {analysis['recommended_driver']}")
                
        # Veri kayıtları
        if "records" in analysis and analysis["records"]:
            if color:
                print(f"\n{colorama.Fore.GREEN}=== Veri Kayıtları ==={colorama.Style.RESET_ALL}")
            else:
                print("\n=== Veri Kayıtları ===")
                
            for i, record in enumerate(analysis["records"]):
                if color:
                    print(f"{colorama.Fore.CYAN}Kayıt #{i+1}:{colorama.Style.RESET_ALL} {record['description']} = {record['value']} {record['unit']}")
                    
                    if record.get("storage", 0) > 0:
                        print(f"  Depolama: {record['storage']}")
                    if record.get("tariff", 0) > 0:
                        print(f"  Tarife: {record['tariff']}")
                    if record.get("function", "") != "Instantaneous value":
                        print(f"  Fonksiyon: {record['function']}")
                else:
                    print(f"Kayıt #{i+1}: {record['description']} = {record['value']} {record['unit']}")
                    
                    if record.get("storage", 0) > 0:
                        print(f"  Depolama: {record['storage']}")
                    if record.get("tariff", 0) > 0:
                        print(f"  Tarife: {record['tariff']}")
                    if record.get("function", "") != "Instantaneous value":
                        print(f"  Fonksiyon: {record['function']}")
        else:
            if analysis.get("encrypted", False):
                if color:
                    print(f"\n{colorama.Fore.YELLOW}Veri alanı şifreli, çözümleme için anahtar gerekiyor.{colorama.Style.RESET_ALL}")
                else:
                    print("\nVeri alanı şifreli, çözümleme için anahtar gerekiyor.")
            else:
                if color:
                    print(f"\n{colorama.Fore.YELLOW}Veri kaydı bulunamadı.{colorama.Style.RESET_ALL}")
                else:
                    print("\nVeri kaydı bulunamadı.")
    
    def print_comparison_results(self, results: Dict[str, Any], color: bool = True) -> None:
        """
        Karşılaştırma sonuçlarını konsola yazdırır
        
        Args:
            results: Karşılaştırma sonuçları
            color: Renkli çıktı kullanılsın mı?
        """
        # Hata kontrolü
        if "error" in results:
            if color:
                print(f"{colorama.Fore.RED}HATA: {results['error']}{colorama.Style.RESET_ALL}")
            else:
                print(f"HATA: {results['error']}")
            return
            
        # Başlık karşılaştırması
        header_comp = results.get("header_comparison", {})
        
        if color:
            print(f"{colorama.Fore.GREEN}=== Başlık Karşılaştırması ==={colorama.Style.RESET_ALL}")
        else:
            print("=== Başlık Karşılaştırması ===")
        
        if header_comp.get("same_meter", False):
            if color:
                print(f"Aynı sayaç: {colorama.Fore.GREEN}Evet{colorama.Style.RESET_ALL}")
            else:
                print("Aynı sayaç: Evet")
        else:
            if color:
                print(f"Aynı sayaç: {colorama.Fore.RED}Hayır{colorama.Style.RESET_ALL}")
            else:
                print("Aynı sayaç: Hayır")
                
        if header_comp.get("same_headers", True):
            if color:
                print(f"Aynı başlık: {colorama.Fore.GREEN}Evet{colorama.Style.RESET_ALL}")
            else:
                print("Aynı başlık: Evet")
        else:
            if color:
                print(f"Aynı başlık: {colorama.Fore.RED}Hayır{colorama.Style.RESET_ALL}")
            else:
                print("Aynı başlık: Hayır")
                
            # Farklılıkları göster
            diffs = header_comp.get("differences", {})
            for field, values in diffs.items():
                if color:
                    print(f"  {field}: {colorama.Fore.YELLOW}{values['telegram1']}{colorama.Style.RESET_ALL} -> {colorama.Fore.CYAN}{values['telegram2']}{colorama.Style.RESET_ALL}")
                else:
                    print(f"  {field}: {values['telegram1']} -> {values['telegram2']}")
        
        # Veri karşılaştırması
        data_comp = results.get("data_comparison", {})
        
        if color:
            print(f"\n{colorama.Fore.GREEN}=== Veri Karşılaştırması ==={colorama.Style.RESET_ALL}")
        else:
            print("\n=== Veri Karşılaştırması ===")
            
        if not data_comp.get("can_compare", False):
            if color:
                print(f"{colorama.Fore.YELLOW}{data_comp.get('message', 'Karşılaştırma yapılamıyor')}{colorama.Style.RESET_ALL}")
            else:
                print(data_comp.get("message", "Karşılaştırma yapılamıyor"))
            return
            
        # İstatistikler
        print(f"Aynı alanlar: {data_comp.get('same_fields_count', 0)}")
        print(f"Farklı alanlar: {data_comp.get('different_fields_count', 0)}")
        print(f"Sadece ilk telegram'da: {data_comp.get('only_in_first_count', 0)}")
        print(f"Sadece ikinci telegram'da: {data_comp.get('only_in_second_count', 0)}")
        
        # Değişen alanlar
        if data_comp.get("different_fields", []):
            if color:
                print(f"\n{colorama.Fore.YELLOW}Değişen Alanlar:{colorama.Style.RESET_ALL}")
            else:
                print("\nDeğişen Alanlar:")
                
            for field in data_comp["different_fields"]:
                desc = field["description"]
                val1 = field["value1"]
                val2 = field["value2"]
                unit = field["unit"]
                diff = field.get("diff")
                
                if color:
                    print(f"  {desc}: {colorama.Fore.YELLOW}{val1}{colorama.Style.RESET_ALL} -> {colorama.Fore.CYAN}{val2}{colorama.Style.RESET_ALL} {unit}")
                else:
                    print(f"  {desc}: {val1} -> {val2} {unit}")
                    
                if diff is not None:
                    if diff > 0:
                        if color:
                            print(f"    Fark: {colorama.Fore.GREEN}+{diff}{colorama.Style.RESET_ALL} {unit}")
                        else:
                            print(f"    Fark: +{diff} {unit}")
                    else:
                        if color:
                            print(f"    Fark: {colorama.Fore.RED}{diff}{colorama.Style.RESET_ALL} {unit}")
                        else:
                            print(f"    Fark: {diff} {unit}")
        
        # Sadece ilk telegram'da olan alanlar
        if data_comp.get("only_in_first", []):
            if color:
                print(f"\n{colorama.Fore.YELLOW}Sadece İlk Telegram'da Olan Alanlar:{colorama.Style.RESET_ALL}")
            else:
                print("\nSadece İlk Telegram'da Olan Alanlar:")
                
            for field in data_comp["only_in_first"]:
                print(f"  {field['description']}: {field['value']} {field['unit']}")
                
        # Sadece ikinci telegram'da olan alanlar
        if data_comp.get("only_in_second", []):
            if color:
                print(f"\n{colorama.Fore.YELLOW}Sadece İkinci Telegram'da Olan Alanlar:{colorama.Style.RESET_ALL}")
            else:
                print("\nSadece İkinci Telegram'da Olan Alanlar:")
                
            for field in data_comp["only_in_second"]:
                print(f"  {field['description']}: {field['value']} {field['unit']}")


class TelegramWatcher:
    """
    Telegram izleyici - Telegram akışını izler ve değişiklikleri raporlar
    
    Bu sınıf donanım olmadan kullanılabilir, ancak gerçek uygulamada
    donanım bağlantısı ile kullanılabilir.
    """
    
    def __init__(self):
        """İzleyici başlatma"""
        self.analyzer = TelegramAnalyzer()
        self.last_telegrams = {}  # meter_id -> telegram_data
        self.history = {}  # meter_id -> [{ data, timestamp }]
        self.max_history = 10  # Her sayaç için maksimum geçmiş
        
    def add_telegram(self, telegram_hex: str) -> Dict[str, Any]:
        """
        Yeni bir telegram ekler ve değişiklikleri raporlar
        
        Args:
            telegram_hex: Telegram hex string
            
        Returns:
            Dict[str, Any]: İşleme sonuçları
        """
        # Analiz et
        analysis = self.analyzer.analyze_telegram(telegram_hex)
        
        # Geçerlilik kontrolü
        if not analysis.get("valid", False):
            return {
                "status": "invalid",
                "message": "Geçersiz telegram",
                "analysis": analysis
            }
            
        # Sayaç ID'si
        meter_id = analysis.get("id")
        if not meter_id:
            return {
                "status": "error",
                "message": "Sayaç ID'si bulunamadı",
                "analysis": analysis
            }
            
        # Telegram verisini temizle
        telegram_data = binascii.unhexlify(telegram_hex.replace(" ", ""))
        
        # Değişiklik kontrolü
        changes = None
        if meter_id in self.last_telegrams:
            # Karşılaştır
            last_data = self.last_telegrams[meter_id]
            
            # Telegram nesnelerini oluştur
            telegram1 = Telegram(last_data)
            telegram2 = Telegram(telegram_data)
            
            # Karşılaştırma sonuçları
            comparison = {
                "header_comparison": self.analyzer._compare_headers(telegram1, telegram2),
                "data_comparison": self.analyzer._compare_data(telegram1, telegram2)
            }
            
            changes = comparison
            
        # Son telegram'ı güncelle
        self.last_telegrams[meter_id] = telegram_data
        
        # Geçmişe ekle
        if meter_id not in self.history:
            self.history[meter_id] = []
            
        # Geçmiş boyutu kontrol et
        if len(self.history[meter_id]) >= self.max_history:
            self.history[meter_id].pop(0)
            
        # Yeni telegram'ı ekle
        self.history[meter_id].append({
            "data": telegram_hex,
            "timestamp": datetime.now().isoformat()
        })
        
        # Sonuç
        result = {
            "status": "success",
            "message": "Telegram işlendi",
            "meter_id": meter_id,
            "analysis": analysis
        }
        
        if changes:
            result["changes"] = changes
            
        return result
    
    def get_meter_history(self, meter_id: str) -> List[Dict[str, Any]]:
        """
        Belirli bir sayaç için geçmişi döndürür
        
        Args:
            meter_id: Sayaç kimliği
            
        Returns:
            List[Dict[str, Any]]: Geçmiş telegraflar
        """
        if meter_id not in self.history:
            return []
            
        return self.history[meter_id]
    
    def get_latest_telegram(self, meter_id: str) -> Optional[bytes]:
        """
        Belirli bir sayaç için en son telegram'ı döndürür
        
        Args:
            meter_id: Sayaç kimliği
            
        Returns:
            Optional[bytes]: En son telegram veya None
        """
        return self.last_telegrams.get(meter_id)
    
    def print_meter_history(self, meter_id: str, color: bool = True) -> None:
        """
        Sayaç geçmişini konsola yazdırır
        
        Args:
            meter_id: Sayaç kimliği
            color: Renkli çıktı kullanılsın mı?
        """
        history = self.get_meter_history(meter_id)
        
        if not history:
            if color:
                print(f"{colorama.Fore.YELLOW}Sayaç geçmişi bulunamadı: {meter_id}{colorama.Style.RESET_ALL}")
            else:
                print(f"Sayaç geçmişi bulunamadı: {meter_id}")
            return
            
        if color:
            print(f"{colorama.Fore.GREEN}=== Sayaç Geçmişi: {meter_id} ==={colorama.Style.RESET_ALL}")
        else:
            print(f"=== Sayaç Geçmişi: {meter_id} ===")
            
        for i, entry in enumerate(reversed(history)):
            timestamp = entry["timestamp"]
            data = entry["data"]
            
            if color:
                print(f"{colorama.Fore.CYAN}Telegram #{i+1}:{colorama.Style.RESET_ALL} {timestamp}")
                print(f"  {data}")
            else:
                print(f"Telegram #{i+1}: {timestamp}")
                print(f"  {data}")


def main() -> None:
    """Komut satırı arayüzü ana fonksiyonu"""
    # Argüman ayrıştırıcı
    parser = argparse.ArgumentParser(description="WMBus/M-Bus Telegram Analiz ve Debug Aracı")
    
    # Alt komutlar
    subparsers = parser.add_subparsers(dest="command", help="Komut")
    
    # Analiz komutu
    analyze_parser = subparsers.add_parser("analyze", help="Telegram analizi")
    analyze_parser.add_argument("telegram", help="Analiz edilecek telegram hex string")
    analyze_parser.add_argument("--key", help="Şifreleme anahtarı (şifreli telegramlar için)")
    analyze_parser.add_argument("--json", action="store_true", help="JSON formatında çıktı")
    analyze_parser.add_argument("--no-color", action="store_true", help="Renksiz çıktı")
    
    # Karşılaştırma komutu
    compare_parser = subparsers.add_parser("compare", help="İki telegram'ı karşılaştır")
    compare_parser.add_argument("telegram1", help="İlk telegram hex string")
    compare_parser.add_argument("telegram2", help="İkinci telegram hex string")
    compare_parser.add_argument("--json", action="store_true", help="JSON formatında çıktı")
    compare_parser.add_argument("--no-color", action="store_true", help="Renksiz çıktı")
    
    # İzleme komutu
    watch_parser = subparsers.add_parser("watch", help="Telegram akışını izle")
    watch_parser.add_argument("--file", help="Telegram'ları içeren dosya (her satırda bir telegram)")
    watch_parser.add_argument("--interval", type=float, default=1.0, help="Dosyayı kontrol etme aralığı (saniye)")
    watch_parser.add_argument("--no-color", action="store_true", help="Renksiz çıktı")
    
    # Argümanları ayrıştır
    args = parser.parse_args()
    
    # Analizci oluştur
    analyzer = TelegramAnalyzer()
    
    # Komuta göre işlem yap
    if args.command == "analyze":
        # Analiz
        if args.key:
            # Şifre çöz ve analiz et
            result = analyzer.decrypt_telegram(args.telegram, args.key)
            
            if result["status"] == "success":
                # Şifre çözme başarılı, çözülmüş telegram'ı analiz et
                analysis = analyzer.analyze_telegram(result["telegram"])
                
                if args.json:
                    print(json.dumps(analysis, indent=2))
                else:
                    analyzer.print_telegram_analysis(analysis, not args.no_color)
            else:
                # Şifre çözme başarısız
                if args.json:
                    print(json.dumps(result, indent=2))
                else:
                    if args.no_color:
                        print(f"HATA: {result['message']}")
                    else:
                        print(f"{colorama.Fore.RED}HATA: {result['message']}{colorama.Style.RESET_ALL}")
        else:
            # Normal analiz
            analysis = analyzer.analyze_telegram(args.telegram)
            
            if args.json:
                print(json.dumps(analysis, indent=2))
            else:
                analyzer.print_telegram_analysis(analysis, not args.no_color)
                
    elif args.command == "compare":
        # Karşılaştırma
        results = analyzer.compare_telegrams(args.telegram1, args.telegram2)
        
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            analyzer.print_comparison_results(results, not args.no_color)
            
    elif args.command == "watch":
        # İzleme
        watcher = TelegramWatcher()
        
        if args.file:
            # Dosya izleme
            last_size = 0
            last_mtime = 0
            
            print(f"Dosya izleniyor: {args.file}")
            
            try:
                while True:
                    # Dosya değişikliği kontrol et
                    try:
                        file_stat = os.stat(args.file)
                        
                        # Değişiklik var mı?
                        if file_stat.st_size != last_size or file_stat.st_mtime != last_mtime:
                            # Dosyayı oku
                            with open(args.file, "r") as f:
                                # Son satırlar
                                lines = f.readlines()
                                
                                # Her satırı işle
                                for line in lines:
                                    # Yorum satırlarını atla
                                    if line.strip().startswith("#"):
                                        continue
                                        
                                    # Boş satırları atla
                                    if not line.strip():
                                        continue
                                        
                                    # Telegram'ı işle
                                    result = watcher.add_telegram(line.strip())
                                    
                                    # Sonucu göster
                                    if result["status"] == "success":
                                        meter_id = result["meter_id"]
                                        
                                        if "changes" in result:
                                            # Değişiklikleri göster
                                            if args.no_color:
                                                print(f"Sayaç değişikliği: {meter_id}")
                                            else:
                                                print(f"{colorama.Fore.GREEN}Sayaç değişikliği: {meter_id}{colorama.Style.RESET_ALL}")
                                                
                                            analyzer.print_comparison_results(result["changes"], not args.no_color)
                                        else:
                                            # İlk telegram
                                            if args.no_color:
                                                print(f"Yeni sayaç: {meter_id}")
                                            else:
                                                print(f"{colorama.Fore.CYAN}Yeni sayaç: {meter_id}{colorama.Style.RESET_ALL}")
                                                
                                            analyzer.print_telegram_analysis(result["analysis"], not args.no_color)
                                    else:
                                        # Hata
                                        if args.no_color:
                                            print(f"Hata: {result['message']}")
                                        else:
                                            print(f"{colorama.Fore.RED}Hata: {result['message']}{colorama.Style.RESET_ALL}")
                            
                            # Dosya bilgilerini güncelle
                            last_size = file_stat.st_size
                            last_mtime = file_stat.st_mtime
                            
                    except FileNotFoundError:
                        if args.no_color:
                            print(f"Dosya bulunamadı: {args.file}")
                        else:
                            print(f"{colorama.Fore.RED}Dosya bulunamadı: {args.file}{colorama.Style.RESET_ALL}")
                            
                    except Exception as e:
                        if args.no_color:
                            print(f"Hata: {e}")
                        else:
                            print(f"{colorama.Fore.RED}Hata: {e}{colorama.Style.RESET_ALL}")
                    
                    # Bekleme
                    time.sleep(args.interval)
                    
            except KeyboardInterrupt:
                print("\nİzleme sonlandırıldı.")
        else:
            print("İzleme için bir dosya belirtilmedi.")
    else:
        parser.print_help()

    
if __name__ == "__main__":
    main()