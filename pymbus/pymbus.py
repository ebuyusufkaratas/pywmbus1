"""
Python WMBus - Ana modül

Bu, Python WMBus'ın ana modülüdür. WMBus/M-Bus telegram'larını işlemek,
çözmek ve çeşitli çıktı formatlarına dönüştürmek için kullanılır.
"""

import os
import sys
import time
import logging
import signal
import argparse
import json
from typing import Dict, List, Optional, Union, Any

from src.meter import Meter
from src.telegram import Telegram
from src.configuration import Configuration
from src.drivers.auto import AutoDriver
root_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(root_dir)
sys.path.append(parent_dir)
# Loglama yapılandırması - daha sonra yapılandırma tarafından değiştirilecek
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('pymbus')

class PyMBus:
    """
    Python WMBus ana uygulama sınıfı

    Bu sınıf, WMBus/M-Bus telegram'larını işleyen ana uygulamayı temsil eder.
    Sayaç yönetimi, telegram işleme ve çıktı oluşturma işlevlerini sağlar.
    """
    
    def __init__(self):
        """PyMBus örneği başlatma"""
        self.meters = []
        self.config = Configuration()
        self.running = False
        self.auto_driver = AutoDriver()  # Otomatik sürücü analizi için
    
    def load_config(self, config_file: Optional[str] = None) -> bool:
        """
        Yapılandırmayı yükler
        
        Args:
            config_file: Yapılandırma dosyası yolu (isteğe bağlı)
            
        Returns:
            bool: Yükleme başarılı mı?
        """
        # Komut satırını ayrıştır
        self.config.parse_command_line()
        
        # Yapılandırma dosyası belirtilmişse yükle
        if config_file:
            return self.config.load_config_file(config_file)
            
        return True
    
    def add_meter(self, name: str, meter_id: str, driver_name: str, key: Optional[str] = None) -> None:
        """
        Yeni bir sayaç ekler
        
        Args:
            name: Sayaç için kullanıcı tanımlı isim
            meter_id: Sayaç kimliği
            driver_name: Kullanılacak sürücü adı
            key: Şifreleme anahtarı (gerekirse)
        """
        meter = Meter(name, meter_id, driver_name, key)
        self.meters.append(meter)
        logger.info(f"Sayaç eklendi: {name} ({meter_id})")
    
    def process_telegram(self, telegram_data: Union[str, bytes]) -> Optional[Meter]:
        """
        Bir telegramı işler
        
        Args:
            telegram_data: İşlenecek telegram verisi
            
        Returns:
            Optional[Meter]: Telegramı işleyen sayaç veya None
        """
        # Telegram nesnesini oluştur
        telegram = Telegram(telegram_data)
        
        # Telegram başlığı geçerli mi?
        if not telegram.header:
            logger.error("Geçersiz telegram başlığı")
            return None
            
        meter_id = telegram.header.meter_id
        logger.debug(f"Telegram alındı: {meter_id} (üretici: {telegram.header.manufacturer})")
        
        # Telegram'ı her sayaç için deneyin
        for meter in self.meters:
            # Sayaç ID'si eşleşiyor mu?
            if meter.id.lower() == meter_id.lower():
                # Telegram'ı işlemeyi dene
                if meter.process_telegram(telegram_data):
                    self._handle_meter_update(meter)
                    return meter
        
        # Eşleşen sayaç bulunamadı veya işleme hatası
        logger.debug(f"Sayaç bulunamadı veya işleme hatası: {meter_id}")
        return None
    
    def analyze_telegram(self, telegram_data: Union[str, bytes]) -> Dict[str, Any]:
        """
        Bir telegramı analiz eder ve uygun sürücüyü önerir
        
        Args:
            telegram_data: İşlenecek telegram verisi
            
        Returns:
            Dict[str, Any]: Telegram analiz sonuçları
        """
        # Telegram nesnesini oluştur
        telegram = Telegram(telegram_data)
        
        # Telegram başlığı geçerli mi?
        if not telegram.header:
            return {"error": "Geçersiz telegram başlığı"}
            
        # Telegram analizi
        result = {
            "manufacturer": telegram.header.manufacturer,
            "meter_id": telegram.header.meter_id,
            "version": f"0x{telegram.header.version:02x}",
            "meter_type": f"0x{telegram.header.meter_type:02x}",
            "is_encrypted": telegram.header.is_encrypted
        }
        
        # En uygun sürücüyü bul
        recommended_driver = self.auto_driver.find_driver(telegram)
        if recommended_driver:
            result["recommended_driver"] = recommended_driver
        
        return result
    
    def _handle_meter_update(self, meter: Meter) -> None:
        """
        Sayaç güncellemelerini işler
        
        Args:
            meter: Güncellenen sayaç
        """
        reading = meter.get_reading()
        
        # Yapılandırmaya göre çıktı oluştur
        if self.config.config['format'] == 'json':
            output = self._format_json_output(meter, reading)
            print(output)
        elif self.config.config['format'] == 'fields':
            output = self._format_fields_output(meter, reading)
            print(output)
        else:  # hr (human readable)
            output = self._format_hr_output(meter, reading)
            print(output)
        
        # Dosyaya kaydet
        if self.config.config['meterfiles']:
            self._save_to_file(meter, reading)
        
        # Shell komutunu çalıştır
        if self.config.config['shell']:
            self._execute_shell_command(meter, reading)
    
    def _format_json_output(self, meter: Meter, reading: Dict[str, Any]) -> str:
        """
        JSON formatında çıktı oluşturur
        
        Args:
            meter: Sayaç
            reading: Okuma verileri
            
        Returns:
            str: JSON formatında çıktı
        """
        # JSON alanlarını ekle
        for field, value in self.config.config['json_fields'].items():
            reading[field] = value
        
        # Pretty print seçeneği
        if self.config.config.get('ppjson', False):
            return json.dumps(reading, indent=2)
        else:
            return json.dumps(reading)
    
    def _format_fields_output(self, meter: Meter, reading: Dict[str, Any]) -> str:
        """
        Alan formatında çıktı oluşturur
        
        Args:
            meter: Sayaç
            reading: Okuma verileri
            
        Returns:
            str: Alan formatında çıktı
        """
        separator = self.config.config['separator']
        
        # Belirli alanlar seçildiyse
        if self.config.config['fields']:
            fields = self.config.config['fields']
        else:
            fields = list(reading.keys())
        
        # Değerleri birleştir
        values = [str(reading.get(field, "")) for field in fields]
        return separator.join(values)
    
    def _format_hr_output(self, meter: Meter, reading: Dict[str, Any]) -> str:
        """
        İnsan okunabilir formatta çıktı oluşturur
        
        Args:
            meter: Sayaç
            reading: Okuma verileri
            
        Returns:
            str: İnsan okunabilir formatta çıktı
        """
        # Basit bir insan okunabilir format
        # Gerçek uygulamada daha özelleştirilebilir olabilir
        parts = [reading.get('name', meter.name), reading.get('id', meter.id)]
        
        # Önemli değerleri ekle
        for key in sorted(reading.keys()):
            if key not in ['name', 'id', 'driver', 'manufacturer', 'timestamp']:
                value = reading[key]
                parts.append(f"{value}")
        
        # Zaman damgası
        if 'timestamp' in reading:
            parts.append(reading['timestamp'])
        
        return ' '.join(map(str, parts))
    
    def _save_to_file(self, meter: Meter, reading: Dict[str, Any]) -> None:
        """
        Okuma verilerini dosyaya kaydeder
        
        Args:
            meter: Sayaç
            reading: Okuma verileri
        """
        # Dosya adını oluştur
        if self.config.config['meterfilesnaming'] == 'name':
            filename = meter.name
        elif self.config.config['meterfilesnaming'] == 'id':
            filename = meter.id
        else:  # name-id
            filename = f"{meter.name}_{meter.id}"
        
        # Zaman damgası ekle
        if self.config.config['meterfilestimestamp'] != 'never':
            from datetime import datetime
            now = datetime.now()
            
            if self.config.config['meterfilestimestamp'] == 'day':
                timestamp = now.strftime('%Y-%m-%d')
            elif self.config.config['meterfilestimestamp'] == 'hour':
                timestamp = now.strftime('%Y-%m-%d_%H')
            elif self.config.config['meterfilestimestamp'] == 'minute':
                timestamp = now.strftime('%Y-%m-%d_%H-%M')
            else:  # micros
                timestamp = now.strftime('%Y-%m-%d_%H-%M-%S-%f')
            
            filename = f"{filename}_{timestamp}"
        
        # Tam dosya yolu
        file_path = os.path.join(self.config.config['meterfiles'], filename)
        
        # Dosyaya yaz
        try:
            # Çıktı formatı
            if self.config.config['format'] == 'json':
                content = self._format_json_output(meter, reading)
            elif self.config.config['format'] == 'fields':
                content = self._format_fields_output(meter, reading)
            else:  # hr
                content = self._format_hr_output(meter, reading)
            
            # Yazma modu (üzerine yazma veya ekleme)
            mode = 'a' if self.config.config['meterfilesaction'] == 'append' else 'w'
            
            with open(file_path, mode) as f:
                f.write(content)
                if self.config.config['meterfilesaction'] == 'append':
                    f.write('\n')
            
            logger.debug(f"Dosyaya yazıldı: {file_path}")
            
        except Exception as e:
            logger.error(f"Dosyaya yazma hatası: {file_path} - {e}")
    
    def _execute_shell_command(self, meter: Meter, reading: Dict[str, Any]) -> None:
        """
        Shell komutunu çalıştırır
        
        Args:
            meter: Sayaç
            reading: Okuma verileri
        """
        import subprocess
        import shlex
        
        # Shell komutu alın
        command = self.config.config['shell']
        if not command:
            return
        
        try:
            # Çevre değişkenlerini oluştur
            env = os.environ.copy()
            
            # Sayaç değerlerini çevre değişkenlerine ekle
            for key, value in reading.items():
                env[f"METER_{key.upper()}"] = str(value)
            
            # JSON formatında tüm veriyi ekle
            env["METER_JSON"] = json.dumps(reading)
            
            # Komutu çalıştır
            subprocess.run(shlex.split(command), env=env, check=True)
            logger.debug(f"Shell komutu çalıştırıldı: {command}")
            
        except Exception as e:
            logger.error(f"Shell komutu hatası: {command} - {e}")
    
    def start(self) -> None:
        """Ana işlem döngüsünü başlatır"""
        self.running = True
        
        # Sinyal işleyicilerini ayarla
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("PyMBus başlatıldı")
        
        while self.running:
            # Bu kısım, gerçek uygulamada veri alma mekanizmasına göre değişecektir
            # Örneğin, donanım olmadan bu kısım sadece test telegraflarıyla çalışabilir
            
            # Test için biraz bekle
            time.sleep(1)
    
    def stop(self) -> None:
        """Uygulamayı durdurur"""
        self.running = False
        logger.info("PyMBus durduruldu")
    
    def _signal_handler(self, sig, frame) -> None:
        """
        Sinyal işleyici
        
        Args:
            sig: Sinyal numarası
            frame: Stack frame
        """
        logger.info(f"Sinyal alındı: {sig}")
        self.stop()

# Ana uygulama örneği
def main():
    """Ana uygulama giriş noktası"""
    app = PyMBus()
    
    try:
        # Yapılandırmayı yükle
        app.load_config()
        
        # Sayaç ekle
        app.add_meter("MyTapWater", "12345678", "multical21", "00112233445566778899AABBCCDDEEFF")
        
        # Uygulamayı başlat
        app.start()
        
    except KeyboardInterrupt:
        logger.info("Kullanıcı tarafından durduruldu")
    except Exception as e:
        logger.error(f"Hata: {e}", exc_info=True)
    finally:
        app.stop()

# Komut satırından çalıştırıldığında
if __name__ == "__main__":
    main()