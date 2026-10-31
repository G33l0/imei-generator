# imei_generator.py
import random

def luhn_checksum(number_str):
    """Calculate the Luhn checksum."""
    def digits_of(n):
        return [int(d) for d in str(n)]
    
    digits = digits_of(number_str)
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    
    checksum = sum(odd_digits)
    for d in even_digits:
        checksum += sum(digits_of(d * 2))
    
    return checksum % 10

def generate_imei_with_tac(tac_prefix):
    """
    Generate a full 15-digit IMEI from an 8-digit TAC prefix.
    Digits 9-14 are a random serial number (SNR).
    Digit 15 is the Luhn check digit.
    """
    if len(tac_prefix) != 8 or not tac_prefix.isdigit():
        raise ValueError("TAC prefix must be an 8-digit numeric string")
    
    snr = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    imei_base = tac_prefix + snr
    checksum = luhn_checksum(imei_base + '0')
    check_digit = (10 - checksum) % 10
    
    return imei_base + str(check_digit)

# Test
if __name__ == "__main__":
    iphone_xr_tac = "35084958"  # Example iPhone XR TAC
    print(f"Test iPhone XR IMEI: {generate_imei_with_tac(iphone_xr_tac)}")