"""
Otomatik sürücü tespiti

Bu modül, telegram'ları analiz ederek en uygun sürücüyü tespit etmek için kullanılır.
Ayrıca, tüm sürücüleri yükleyip yönetmek için de kullanılabilir.
"""

import logging
import importlib
import pkgutil
from typing import Dict, Optional, Any, List, Type

# Mutlak import
from pymbus.src.telegram import Telegram
from pymbus.src.drivers.driver_base import DriverBase

logger = logging.getLogger(__name__)

class AutoDriver:
    """Otomatik sürücü tespiti sınıfı"""
    
    def __init__(self):
        """Sürücü başlatma"""
        self.drivers = []
        self._load_all_drivers()
    
    def _load_all_drivers(self) -> None:
        """Tüm kullanılabilir sürücüleri yükler"""
        try:
            # Drivers paketindeki tüm kategorileri tara
            from pymbus.src import drivers as drivers_pkg
            
            # Önce kök sürücüleri yükle
            for _, name, is_pkg in pkgutil.iter_modules(drivers_pkg.__path__):
                # Kategori mi yoksa direkt sürücü mü?
                if not is_pkg and name not in ['auto', 'driver_base']:
                    try:
                        # Modülü içe aktar
                        driver_module = importlib.import_module(f".{name}", "pymbus.src.drivers")
                        
                        # Sınıf adını tahmin et (ör. multical21 -> Multical21Driver)
                        class_name = f"{name.capitalize()}Driver"
                        
                        if hasattr(driver_module, class_name):
                            driver_class = getattr(driver_module, class_name)
                            driver = driver_class()
                            self.drivers.append(driver)
                            logger.debug(f"Kök sürücü yüklendi: {name}")
                    except Exception as e:
                        logger.error(f"Sürücü yükleme hatası: {name} - {e}")
            
            # Şimdi kategorilerdeki sürücüleri yükle
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
                                logger.debug(f"Sürücü yüklendi: {name}.{driver_name}")
                        except Exception as e:
                            logger.error(f"Sürücü yükleme hatası: {name}.{driver_name} - {e}")
            
            logger.info(f"Toplam {len(self.drivers)} sürücü yüklendi")
            for driver in self.drivers:
                logger.info(f"Yüklenen sürücü: {driver.name}, üreticiler: {driver.manufacturer_codes}, tipler: {driver.meter_types}")
        except ImportError as e:
            logger.warning(f"Sürücü yükleme hatası: {e}")
            # Temel import hatası - muhtemelen paket yapısı hazır değil
            # Test amaçlı çalışmaya devam edilebilir
    
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
    
    def get_driver_by_name(self, driver_name: str) -> Optional[DriverBase]:
        """
        İsimle sürücü bulur
        
        Args:
            driver_name: Sürücü adı
            
        Returns:
            Optional[DriverBase]: Sürücü veya None
        """
        for driver in self.drivers:
            if driver.name.lower() == driver_name.lower():
                return driver
        
        return None
    
    def get_driver_for_meter(self, manufacturer: str, meter_type: int, version: int) -> Optional[DriverBase]:
        """
        Sayaç parametrelerine göre sürücü bulur
        
        Args:
            manufacturer: Üretici kodu
            meter_type: Sayaç tipi
            version: Versiyon
            
        Returns:
            Optional[DriverBase]: Sürücü veya None
        """
        # Tüm sürücüleri kontrol et
        for driver in self.drivers:
            # Üretici kontrolü
            if driver.manufacturer_codes and manufacturer not in driver.manufacturer_codes:
                continue
                
            # Sayaç tipi kontrolü
            if driver.meter_types and meter_type not in driver.meter_types:
                continue
                
            # Versiyon kontrolü
            if driver.meter_versions and version not in driver.meter_versions:
                continue
                
            # Tüm kriterler eşleşti
            return driver
        
        return None
    
    def get_drivers_list(self) -> List[Dict[str, Any]]:
        """
        Tüm sürücülerin listesini döndürür
        
        Returns:
            List[Dict[str, Any]]: Sürücü bilgileri listesi
        """
        result = []
        
        for driver in self.drivers:
            info = {
                "name": driver.name,
                "description": driver.description,
                "manufacturers": driver.manufacturer_codes,
                "meter_types": driver.meter_types,
                "versions": driver.meter_versions
            }
            result.append(info)
        
        return result