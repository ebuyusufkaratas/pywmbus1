"""
Konfigürasyon işleme modülü

Bu modül, yapılandırma dosyaları ve komut satırı argümanlarını işlemek için
kullanılır. Sayaç tanımlarını yönetmek ve program davranışını yapılandırmak
için gerekli işlevleri sağlar.
"""
import os
import sys
import logging
import json
import configparser
from typing import Dict, List, Optional, Any, Tuple
import argparse

from .meter import Meter, create_meter

logger = logging.getLogger(__name__)

class Configuration:
    """WMBus yapılandırma yöneticisi"""
    
    def __init__(self):
        """Yapılandırma başlatma"""
        self.meters = []
        self.config = {
            "loglevel": "info",
            "format": "json",
            "logtelegrams": False,
            "logfile": None,
            "meterfiles": None,
            "meterfilesaction": "overwrite",
            "meterfilesnaming": "name",
            "meterfilestimestamp": "day",
            "shell": None,
            "separator": ";",
            "fields": [],
            "json_fields": {},
            "donotprobe": []
        }
    
    def load_config_file(self, config_file: str) -> bool:
        """
        Yapılandırma dosyasını yükler
        
        Args:
            config_file: Yapılandırma dosyası yolu
            
        Returns:
            bool: Yükleme başarılı mı?
        """
        if not os.path.isfile(config_file):
            logger.error(f"Yapılandırma dosyası bulunamadı: {config_file}")
            return False
            
        try:
            parser = configparser.ConfigParser(allow_no_value=True)
            parser.read(config_file)
            
            # Genel yapılandırma ayarları
            if 'DEFAULT' in parser:
                section = parser['DEFAULT']
                
                if 'loglevel' in section:
                    self.config['loglevel'] = section['loglevel']
                    
                if 'format' in section:
                    self.config['format'] = section['format']
                    
                if 'logtelegrams' in section:
                    self.config['logtelegrams'] = section.getboolean('logtelegrams')
                    
                if 'logfile' in section:
                    self.config['logfile'] = section['logfile']
                    
                if 'meterfiles' in section:
                    self.config['meterfiles'] = section['meterfiles']
                    
                if 'meterfilesaction' in section:
                    self.config['meterfilesaction'] = section['meterfilesaction']
                    
                if 'meterfilesnaming' in section:
                    self.config['meterfilesnaming'] = section['meterfilesnaming']
                    
                if 'meterfilestimestamp' in section:
                    self.config['meterfilestimestamp'] = section['meterfilestimestamp']
                    
                if 'shell' in section:
                    self.config['shell'] = section['shell']
                    
                if 'separator' in section:
                    self.config['separator'] = section['separator']
                    
                if 'donotprobe' in section:
                    self.config['donotprobe'] = section['donotprobe'].split(',')
                
                # JSON alan eklemeleri
                for key in section:
                    if key.startswith('field_') or key.startswith('json_'):
                        field_name = key.replace('field_', '').replace('json_', '')
                        self.config['json_fields'][field_name] = section[key]
            
            # Sayaç yapılandırması
            meters_dir = os.path.join(os.path.dirname(config_file), 'pymbus.d')
            if os.path.isdir(meters_dir):
                self._load_meters_from_directory(meters_dir)
            
            logger.info(f"Yapılandırma dosyası yüklendi: {config_file}")
            return True
            
        except Exception as e:
            logger.error(f"Yapılandırma dosyası yükleme hatası: {e}", exc_info=True)
            return False
    
    def _load_meters_from_directory(self, directory: str) -> None:
        """
        Belirtilen dizindeki sayaç yapılandırma dosyalarını yükler
        
        Args:
            directory: Sayaç yapılandırma dosyalarının bulunduğu dizin
        """
        if not os.path.isdir(directory):
            logger.warning(f"Sayaç dizini bulunamadı: {directory}")
            return
            
        logger.info(f"Sayaç dizini taranıyor: {directory}")
        
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            
            if not os.path.isfile(file_path):
                continue
                
            try:
                parser = configparser.ConfigParser()
                parser.read(file_path)
                
                if 'DEFAULT' not in parser:
                    logger.warning(f"Geçersiz sayaç yapılandırması: {file_path}")
                    continue
                    
                section = parser['DEFAULT']
                required_fields = ['name', 'id', 'driver']
                
                if not all(field in section for field in required_fields):
                    logger.warning(f"Eksik sayaç parametreleri: {file_path}")
                    continue
                    
                name = section['name']
                meter_id = section['id']
                driver = section['driver']
                key = section.get('key', None)
                meter_type = section.get('type', 'auto')
                
                # Sayaç özel shell komutu
                shell = section.get('shell', None)
                
                # Sayaç özel JSON alanları
                json_fields = {}
                for key_name in section:
                    if key_name.startswith('field_') or key_name.startswith('json_'):
                        field_name = key_name.replace('field_', '').replace('json_', '')
                        json_fields[field_name] = section[key_name]
                
                # Sayaç ekle
                meter = create_meter(meter_type, name, meter_id, driver, key)
                meter_info = {
                    'meter': meter,
                    'shell': shell,
                    'json_fields': json_fields
                }
                self.meters.append(meter_info)
                
                logger.info(f"Sayaç yüklendi: {name} ({meter_id})")
                
            except Exception as e:
                logger.error(f"Sayaç yapılandırma hatası: {file_path} - {e}")
    
    def parse_command_line(self) -> bool:
        """
        Komut satırı argümanlarını ayrıştırır
        
        Returns:
            bool: Ayrıştırma başarılı mı?
        """
        parser = argparse.ArgumentParser(description='Python WMBus Meter Reader')
        
        # Genel seçenekler
        parser.add_argument('--debug', action='store_true', help='Debug modu aktif')
        parser.add_argument('--verbose', action='store_true', help='Ayrıntılı çıktı')
        parser.add_argument('--silent', action='store_true', help='Sessiz mod')
        parser.add_argument('--format', choices=['json', 'fields', 'hr'], 
                          help='Çıktı formatı')
        parser.add_argument('--logtelegrams', action='store_true', 
                          help='Telegram içeriğini logla')
        parser.add_argument('--separator', help='Alan ayırıcı')
        parser.add_argument('--logfile', help='Log dosyası')
        parser.add_argument('--useconfig', help='Yapılandırma dizini')
        parser.add_argument('--meterfiles', help='Sayaç okuma dosyaları dizini')
        parser.add_argument('--meterfilesaction', choices=['overwrite', 'append'],
                          help='Dosya güncelleme modu')
        parser.add_argument('--selectfields', help='Seçilecek alan listesi')
        parser.add_argument('--shell', help='Kabuk komutu')
        parser.add_argument('--analyze', nargs='?', const=True, 
                          help='Telegram analizi yap')
        parser.add_argument('--donotprobe', action='append', 
                         help='Taranmayacak cihazlar (bir veya daha fazla)')
        
        # Komut satırındaki diğer argümanları ayrıştır (device ve meters)
        parser.add_argument('args', nargs='*', help='Diğer argümanlar')
        
        args = parser.parse_args()
        
        # Log seviyesini ayarla
        if args.debug:
            self.config['loglevel'] = 'debug'
        elif args.verbose:
            self.config['loglevel'] = 'info'
        elif args.silent:
            self.config['loglevel'] = 'error'
        
        # Diğer seçenekleri ayarla
        if args.format:
            self.config['format'] = args.format
            
        if args.logtelegrams:
            self.config['logtelegrams'] = True
            
        if args.separator:
            self.config['separator'] = args.separator
            
        if args.logfile:
            self.config['logfile'] = args.logfile
            
        if args.meterfiles:
            self.config['meterfiles'] = args.meterfiles
            
        if args.meterfilesaction:
            self.config['meterfilesaction'] = args.meterfilesaction
            
        if args.selectfields:
            self.config['fields'] = args.selectfields.split(',')
            
        if args.shell:
            self.config['shell'] = args.shell
            
        if args.donotprobe:
            self.config['donotprobe'] = args.donotprobe
        
        # Yapılandırma dosyası yükle
        if args.useconfig:
            config_file = os.path.join(args.useconfig, 'pymbus.conf')
            self.load_config_file(config_file)
            
        # Komut satırındaki sayaçları işle
        # Format: [device] [name] [driver] [id] [key]
        # veya [name] [driver] [id] [key] ... vb.
        if args.args:
            # Sayaç dörtlülerini işle
            i = 0
            while i < len(args.args):
                remaining = len(args.args) - i
                
                # En az 4 argüman gerekli (name, driver, id, key)
                if remaining >= 4:
                    name = args.args[i]
                    driver = args.args[i+1]
                    meter_id = args.args[i+2]
                    key = args.args[i+3]
                    
                    # NOKEY ifadesi için boş anahtar
                    if key.upper() == 'NOKEY':
                        key = None
                    
                    # Sayaç ekle
                    meter_type = 'auto'  # Komut satırında açıkça belirtilmediği için otomatik tip
                    meter = create_meter(meter_type, name, meter_id, driver, key)
                    meter_info = {
                        'meter': meter,
                        'shell': None,  # Komut satırı sayaçları için özel shell yok
                        'json_fields': {}  # Komut satırı sayaçları için özel alanlar yok
                    }
                    self.meters.append(meter_info)
                    
                    logger.info(f"Komut satırından sayaç eklendi: {name} ({meter_id})")
                    
                    # Sonraki sayaça geç
                    i += 4
                else:
                    # Kalan argümanlar sayaç dörtlüsü oluşturmak için yetersiz
                    logger.warning(f"Eksik sayaç parametreleri: {args.args[i:]}")
                    break
        
        return True
    
    def setup_logging(self) -> None:
        """Log yapılandırmasını ayarlar"""
        log_levels = {
            'debug': logging.DEBUG,
            'info': logging.INFO,
            'warning': logging.WARNING,
            'error': logging.ERROR,
            'critical': logging.CRITICAL
        }
        
        log_level = log_levels.get(self.config['loglevel'].lower(), logging.INFO)
        
        # Kök logger yapılandırması
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        
        # Varolan tüm handler'ları temizle
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Konsol handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # Dosya handler (belirtilmişse)
        if self.config['logfile']:
            try:
                # Dosya dizinini oluştur (gerekirse)
                log_dir = os.path.dirname(self.config['logfile'])
                if log_dir and not os.path.exists(log_dir):
                    os.makedirs(log_dir)
                    
                file_handler = logging.FileHandler(self.config['logfile'])
                file_handler.setLevel(log_level)
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)
                
                logger.info(f"Log dosyası: {self.config['logfile']}")
            except Exception as e:
                logger.error(f"Log dosyası oluşturma hatası: {e}")
    
    def add_meter(self, name: str, meter_id: str, driver_name: str, meter_type: str = 'auto', key: Optional[str] = None) -> None:
        """
        Yeni bir sayaç ekler
        
        Args:
            name: Sayaç için kullanıcı tanımlı isim
            meter_id: Sayaç kimliği
            driver_name: Kullanılacak sürücü adı
            meter_type: Sayaç tipi ('water', 'heat', 'electricity', 'gas', 'auto')
            key: Şifreleme anahtarı (isteğe bağlı)
        """
        # Sayaç oluştur
        meter = create_meter(meter_type, name, meter_id, driver_name, key)
        
        # Sayaç bilgilerini ekle
        meter_info = {
            'meter': meter,
            'shell': None,
            'json_fields': {}
        }
        
        # Listeye ekle
        self.meters.append(meter_info)
        logger.info(f"Sayaç eklendi: {name} ({meter_id})")
    
    def get_meter_by_id(self, meter_id: str) -> Optional[Meter]:
        """
        ID'ye göre sayaç bulur
        
        Args:
            meter_id: Sayaç kimliği
            
        Returns:
            Optional[Meter]: Sayaç veya None
        """
        for meter_info in self.meters:
            if meter_info['meter'].id.lower() == meter_id.lower():
                return meter_info['meter']
                
        return None
    
    def get_meter_by_name(self, name: str) -> Optional[Meter]:
        """
        İsme göre sayaç bulur
        
        Args:
            name: Sayaç adı
            
        Returns:
            Optional[Meter]: Sayaç veya None
        """
        for meter_info in self.meters:
            if meter_info['meter'].name.lower() == name.lower():
                return meter_info['meter']
                
        return None
    
    def get_meter_info(self, meter: Meter) -> Dict[str, Any]:
        """
        Sayaç için ek bilgileri alır (shell, json_fields, vb.)
        
        Args:
            meter: Sayaç
            
        Returns:
            Dict[str, Any]: Sayaç ek bilgileri veya boş sözlük
        """
        for meter_info in self.meters:
            if meter_info['meter'] == meter:
                return {
                    'shell': meter_info['shell'],
                    'json_fields': meter_info['json_fields']
                }
                
        return {'shell': None, 'json_fields': {}}
    
    def get_meters_list(self) -> List[Dict[str, Any]]:
        """
        Tüm sayaçların listesini döndürür
        
        Returns:
            List[Dict[str, Any]]: Sayaç bilgileri listesi
        """
        result = []
        
        for meter_info in self.meters:
            meter = meter_info['meter']
            info = {
                'name': meter.name,
                'id': meter.id,
                'driver': meter.driver_name,
                'type': getattr(meter, 'meter_type', 'unknown'),
                'link_mode': meter.link_mode.value,
                'has_key': bool(meter.key),
            }
            result.append(info)
        
        return result
    
    def save_config(self, config_file: str) -> bool:
        """
        Yapılandırmayı dosyaya kaydeder
        
        Args:
            config_file: Yapılandırma dosyası yolu
            
        Returns:
            bool: Kaydetme başarılı mı?
        """
        try:
            # Yapılandırma parser'ı oluştur
            parser = configparser.ConfigParser()
            
            # Ana yapılandırma
            parser['DEFAULT'] = {
                'loglevel': self.config['loglevel'],
                'format': self.config['format'],
                'logtelegrams': str(self.config['logtelegrams']),
                'logfile': self.config['logfile'] or '',
                'meterfiles': self.config['meterfiles'] or '',
                'meterfilesaction': self.config['meterfilesaction'],
                'meterfilesnaming': self.config['meterfilesnaming'],
                'meterfilestimestamp': self.config['meterfilestimestamp'],
                'shell': self.config['shell'] or '',
                'separator': self.config['separator'],
                'donotprobe': ','.join(self.config['donotprobe'])
            }
            
            # JSON alanlarını ekle
            for field, value in self.config['json_fields'].items():
                parser['DEFAULT'][f'field_{field}'] = str(value)
            
            # Yapılandırma dizinini oluştur (gerekirse)
            config_dir = os.path.dirname(config_file)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir)
                
            # Dosyaya kaydet
            with open(config_file, 'w') as f:
                parser.write(f)
                
            # Sayaçları ayrı dosyalara kaydet
            meters_dir = os.path.join(os.path.dirname(config_file), 'pymbus.d')
            if not os.path.exists(meters_dir):
                os.makedirs(meters_dir)
                
            # Var olan sayaç dosyalarını temizle
            for filename in os.listdir(meters_dir):
                file_path = os.path.join(meters_dir, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    
            # Sayaçları kaydet
            for i, meter_info in enumerate(self.meters):
                meter = meter_info['meter']
                
                # Sayaç yapılandırması oluştur
                meter_parser = configparser.ConfigParser()
                meter_parser['DEFAULT'] = {
                    'name': meter.name,
                    'id': meter.id,
                    'driver': meter.driver_name,
                    'type': getattr(meter, 'meter_type', 'auto'),
                }
                
                # Anahtar varsa ekle
                if meter.key:
                    meter_parser['DEFAULT']['key'] = meter.key
                    
                # Özel shell varsa ekle
                if meter_info['shell']:
                    meter_parser['DEFAULT']['shell'] = meter_info['shell']
                    
                # Özel JSON alanları varsa ekle
                for field, value in meter_info['json_fields'].items():
                    meter_parser['DEFAULT'][f'field_{field}'] = str(value)
                    
                # Dosyaya kaydet
                meter_file = os.path.join(meters_dir, f"{meter.name}.conf")
                with open(meter_file, 'w') as f:
                    meter_parser.write(f)
                    
            logger.info(f"Yapılandırma kaydedildi: {config_file}")
            return True
            
        except Exception as e:
            logger.error(f"Yapılandırma kaydetme hatası: {e}", exc_info=True)
            return False