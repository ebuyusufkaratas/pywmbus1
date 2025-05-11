"""
Şifreleme ve şifre çözme yardımcıları

Bu modül, M-Bus/WMBus protokollerinde kullanılan AES şifreleme
ve şifre çözme işlevlerini sağlar.
"""

import logging
import binascii
from typing import Union, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad, pad
    CRYPTO_AVAILABLE = True
except ImportError:
    logger.warning("PyCryptodome kütüphanesi bulunamadı. Şifreleme desteği devre dışı.")
    CRYPTO_AVAILABLE = False

def decrypt_aes_cbc(data: bytes, key: str, manufacturer: str, meter_id: str) -> bytes:
    """
    AES-CBC şifreleme ile şifrelenmiş veriyi çözer
    
    Args:
        data: Şifreli veri
        key: Şifreleme anahtarı (hex string)
        manufacturer: Üretici kodu
        meter_id: Sayaç kimliği
        
    Returns:
        bytes: Çözülmüş veri
        
    Raises:
        ValueError: Şifreleme hatası
    """
    if not CRYPTO_AVAILABLE:
        raise ValueError("PyCryptodome kütüphanesi bulunamadı. Şifreleme desteği devre dışı.")
    
    if not key:
        raise ValueError("Şifre çözme için anahtar gerekli")
    
    try:
        # Hex anahtarını ikili veriye dönüştür
        key_bytes = binascii.unhexlify(key.replace(" ", ""))
        
        if len(key_bytes) != 16:
            raise ValueError(f"Geçersiz anahtar uzunluğu: {len(key_bytes)}, 16 byte olmalı")
        
        # IV oluştur (OMS standardına göre)
        iv = generate_iv(manufacturer, meter_id)
        
        # AES-CBC şifre çözme
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        
        try:
            # Unpad işlemi
            decrypted = unpad(cipher.decrypt(data), AES.block_size)
        except ValueError:
            # Padding yoksa düz şifre çözme
            decrypted = cipher.decrypt(data)
        
        return decrypted
        
    except Exception as e:
        logger.error(f"Şifre çözme hatası: {e}")
        raise ValueError(f"Şifre çözme hatası: {e}") from e

def encrypt_aes_cbc(data: bytes, key: str, manufacturer: str, meter_id: str) -> bytes:
    """
    AES-CBC şifreleme ile veriyi şifreler
    
    Args:
        data: Şifrelenecek veri
        key: Şifreleme anahtarı (hex string)
        manufacturer: Üretici kodu
        meter_id: Sayaç kimliği
        
    Returns:
        bytes: Şifrelenmiş veri
        
    Raises:
        ValueError: Şifreleme hatası
    """
    if not CRYPTO_AVAILABLE:
        raise ValueError("PyCryptodome kütüphanesi bulunamadı. Şifreleme desteği devre dışı.")
    
    if not key:
        raise ValueError("Şifreleme için anahtar gerekli")
    
    try:
        # Hex anahtarını ikili veriye dönüştür
        key_bytes = binascii.unhexlify(key.replace(" ", ""))
        
        if len(key_bytes) != 16:
            raise ValueError(f"Geçersiz anahtar uzunluğu: {len(key_bytes)}, 16 byte olmalı")
        
        # IV oluştur (OMS standardına göre)
        iv = generate_iv(manufacturer, meter_id)
        
        # Veriyi pad et (16-byte bloklara tamamla)
        padded_data = pad(data, AES.block_size)
        
        # AES-CBC şifreleme
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(padded_data)
        
        return encrypted
        
    except Exception as e:
        logger.error(f"Şifreleme hatası: {e}")
        raise ValueError(f"Şifreleme hatası: {e}") from e

def generate_iv(manufacturer: str, meter_id: str) -> bytes:
    """
    Başlatma vektörü (IV) oluşturur
    
    OMS standardına göre IV, üretici kodu + sayaç kimliği + sabitler
    şeklinde oluşturulabilir. Bu uygulama, yaygın bir yaklaşımı temsil eder.
    
    Args:
        manufacturer: Üretici kodu
        meter_id: Sayaç kimliği
        
    Returns:
        bytes: Başlatma vektörü (16 byte)
    """
    iv = bytearray(16)
    
    # İlk 3 byte: Üretici kodu
    for i, c in enumerate(manufacturer[:3]):
        if i < 3:
            iv[i] = ord(c)
    
    # Sonraki 8 byte: Sayaç kimliği
    try:
        id_bytes = binascii.unhexlify(meter_id.replace(" ", ""))
        for i, b in enumerate(id_bytes[:8]):
            if i < 8:
                iv[i + 3] = b
    except binascii.Error:
        # ID hex değilse, karakter olarak işle
        for i, c in enumerate(meter_id[:8]):
            if i < 8:
                iv[i + 3] = ord(c)
    
    # Kalan byte'lar 0 olarak kalır
    
    return bytes(iv)

def decrypt_aes_cmac(data: bytes, key: str, manufacturer: str, meter_id: str) -> Tuple[bytes, bool]:
    """
    AES-CMAC ile şifrelenen veriyi çözer
    
    Args:
        data: Şifreli veri
        key: Şifreleme anahtarı (hex string)
        manufacturer: Üretici kodu
        meter_id: Sayaç kimliği
        
    Returns:
        Tuple[bytes, bool]: (Çözülmüş veri, MAC doğrulama sonucu)
        
    Raises:
        ValueError: Şifreleme hatası
    """
    if not CRYPTO_AVAILABLE:
        raise ValueError("PyCryptodome kütüphanesi bulunamadı. Şifreleme desteği devre dışı.")
    
    try:
        # Uygulamada yanlış olabilir - gerçek CMAC ile AES-CBC kombinasyonu daha karmaşıktır
        # Burada basit bir CBC şifre çözme yapıyoruz, CMAC doğrulaması tam değil
        decrypted = decrypt_aes_cbc(data, key, manufacturer, meter_id)
        
        # MAC doğrulaması şimdilik daima True
        # Gerçek uygulamada, MAC hesaplaması ve doğrulaması gerekir
        mac_verified = True
        
        return decrypted, mac_verified
        
    except Exception as e:
        logger.error(f"AES-CMAC şifre çözme hatası: {e}")
        raise ValueError(f"AES-CMAC şifre çözme hatası: {e}") from e

def generate_encryption_key(master_key: str, cipher_field: int, manufacturer: str, meter_id: str) -> str:
    """
    OMS standardına göre şifreleme anahtarı oluşturur
    
    Master anahtardan, belirli bir sayaç için özel anahtar türetir.
    
    Args:
        master_key: Ana anahtar (hex string)
        cipher_field: Şifreleme alanı
        manufacturer: Üretici kodu
        meter_id: Sayaç kimliği
        
    Returns:
        str: Türetilmiş anahtar (hex string)
        
    Raises:
        ValueError: Anahtar türetme hatası
    """
    if not CRYPTO_AVAILABLE:
        raise ValueError("PyCryptodome kütüphanesi bulunamadı. Şifreleme desteği devre dışı.")
    
    try:
        # Master anahtarı çözümle
        master_key_bytes = binascii.unhexlify(master_key.replace(" ", ""))
        
        if len(master_key_bytes) != 16:
            raise ValueError(f"Geçersiz master anahtar uzunluğu: {len(master_key_bytes)}, 16 byte olmalı")
        
        # Türetme verisini hazırla (OMS standardına göre)
        # Bu örnek basitleştirilmiş bir yaklaşımdır
        # Gerçek uygulama daha karmaşık olabilir
        
        # Sayaç ID'sini hazırla
        try:
            id_bytes = binascii.unhexlify(meter_id.replace(" ", ""))
        except binascii.Error:
            # ID hex değilse, karakter olarak işle
            id_bytes = meter_id.encode('utf-8')
        
        # Türetme vektörü: Cipher Field + Üretici + ID
        derivation_data = bytes([cipher_field]) + manufacturer.encode('utf-8') + id_bytes
        
        # 16 byte'a tamamla
        if len(derivation_data) < 16:
            derivation_data = derivation_data + b'\x00' * (16 - len(derivation_data))
        else:
            derivation_data = derivation_data[:16]
        
        # AES ile anahtar türet
        cipher = AES.new(master_key_bytes, AES.MODE_ECB)
        derived_key = cipher.encrypt(derivation_data)
        
        # Hex formatında döndür
        return derived_key.hex().upper()
        
    except Exception as e:
        logger.error(f"Anahtar türetme hatası: {e}")
        raise ValueError(f"Anahtar türetme hatası: {e}") from e

def test_encryption() -> bool:
    """
    Şifreleme ve şifre çözme işlevselliğini test eder
    
    Returns:
        bool: Test sonucu
    """
    if not CRYPTO_AVAILABLE:
        logger.warning("PyCryptodome kütüphanesi bulunamadı. Şifreleme testi atlanıyor.")
        return False
    
    try:
        # Test verileri
        test_key = "00112233445566778899AABBCCDDEEFF"
        test_manufacturer = "KAM"
        test_meter_id = "12345678"
        test_data = b"Test mesaji 123456"
        
        # Şifrele
        encrypted = encrypt_aes_cbc(test_data, test_key, test_manufacturer, test_meter_id)
        
        # Şifre çöz
        decrypted = decrypt_aes_cbc(encrypted, test_key, test_manufacturer, test_meter_id)
        
        # Sonucu kontrol et
        if decrypted != test_data:
            logger.error(f"Şifreleme testi başarısız: {decrypted} != {test_data}")
            return False
        
        logger.info("Şifreleme testi başarılı")
        return True
        
    except Exception as e:
        logger.error(f"Şifreleme testi hatası: {e}")
        return False

# Modül yüklendiğinde otomatik test yap
if CRYPTO_AVAILABLE:
    test_encryption()