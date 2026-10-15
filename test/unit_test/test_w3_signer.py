"""Signer EIP-712 (SDD 5.2/5.6): tái tạo đúng chữ ký của vector dùng chung; không lộ khóa; che log."""
import logging

import pytest

from slopee_web3.adapters.env_signer import EnvKeySigner, recover_personal_sign
from slopee_web3.adapters.logging_filter import SensitiveDataFilter, redact
from slopee_web3.domain.quote import OrderQuote
from w3_support import ADDR, KEYS, VECTORS, make_signer, sign_message


def _quote(m):
    return OrderQuote(orderId=int(m['orderId']), buyer=m['buyer'], merchant=m['merchant'], token=m['token'],
                      amount=int(m['amount']), inspectionDuration=int(m['inspectionDuration']),
                      disputeTimeout=int(m['disputeTimeout']), feeBps=int(m['feeBps']), docHash=m['docHash'],
                      deadline=int(m['deadline']))


@pytest.mark.parametrize('v', VECTORS['orderQuote'], ids=lambda v: v['name'])
def test_signer_reproduces_shared_vector_signature_byte_for_byte(v):
    sig = make_signer().sign_quote(_quote(v['message']))
    assert sig == v['signature']                    # ECDSA tất định (RFC 6979) -> cùng khóa, cùng digest, cùng chữ ký
    assert len(sig) == 132 and sig[-2:] in ('1b', '1c')


def test_signer_addresses_are_checksummed_and_distinct():
    s = make_signer()
    assert s.sender_address('quote_signer') == ADDR['quote_signer']
    assert s.to_checksum(ADDR['buyer'].lower()) == ADDR['buyer']


def test_signer_rejects_duplicate_role_keys():
    with pytest.raises(RuntimeError):
        make_signer(arbitrator_key=KEYS['quote_signer'])
    with pytest.raises(RuntimeError):
        make_signer(shipper_key=KEYS['quote_signer'])


def test_signer_rejects_garbage_key_without_echoing_it():
    with pytest.raises(RuntimeError) as e:
        EnvKeySigner(quote_key='not-a-key-SECRETVALUE', chain_id=1, verifying_contract=ADDR['buyer'])
    assert 'SECRETVALUE' not in str(e.value)


def test_repr_and_attributes_do_not_leak_private_key():
    s = make_signer()
    assert KEYS['quote_signer'][2:] not in repr(s) and KEYS['quote_signer'][2:] not in str(s)
    assert not hasattr(s, 'private_key') and not hasattr(s, 'key')


def test_verify_against_chain_fails_when_role_missing():
    class Chain:
        def has_role(self, role, addr):
            return role != 'SHIPPER_ROLE'
    with pytest.raises(RuntimeError) as e:
        make_signer().verify_against_chain(Chain())
    assert 'SHIPPER_ROLE' in str(e.value)


def test_recover_personal_sign_roundtrip_and_garbage():
    sig = '0x' + sign_message('buyer', 'xin chào').removeprefix('0x')
    assert recover_personal_sign('xin chào', sig) == ADDR['buyer'].lower()
    assert recover_personal_sign('khác', sig) != ADDR['buyer'].lower()
    with pytest.raises(ValueError):
        recover_personal_sign('x', '0x' + '00' * 65)


def test_log_redaction_masks_secrets_but_keeps_tx_hashes(caplog):
    tx = '0x' + '12' * 32
    text = redact(f"signature=0x{'ab' * 65} private_key: {KEYS['buyer']} mnemonic=\"a b\" tx {tx}")
    assert 'ab' * 65 not in text and KEYS['buyer'][2:] not in text and tx in text
    logger = logging.getLogger('w3.redact.test')
    logger.addFilter(SensitiveDataFilter())
    with caplog.at_level(logging.INFO, logger='w3.redact.test'):
        logger.info('relayer key=%s', KEYS['buyer'])
    assert KEYS['buyer'][2:] not in caplog.text and '[REDACTED]' in caplog.text
