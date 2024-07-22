from codecs import encode

from psycopg2.extensions import Binary


class RedshiftBinary(Binary):
    def getquoted(self) -> bytes:
        hex_encoded = encode(self.adapted, "hex_codec")
        statement = b"to_varbyte('%s', 'hex')::varbyte" % hex_encoded
        return statement
