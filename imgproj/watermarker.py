import numpy
from pywt import dwt2, idwt2
from scipy.stats import pearsonr
from scipy import mean
from scipy.misc import toimage
from random import Random
from reedsolo import RSCodec, ReedSolomonError
#from skimage.filter import tv_denoise
from skimage.exposure import rescale_intensity


def iterbits(data):
    if isinstance(data, str):
        data = [ord(ch) for ch in data]
    for n in data:
        for i in (7,6,5,4,3,2,1,0):
            yield (n >> i) & 1

#def rgb_to_ycbcr(img):
#    R = img[:,:,0]
#    G = img[:,:,1]
#    B = img[:,:,2]
#    Y =        (0.299    * R) + (0.587    * G) + (0.114    * B)
#    Cb = 128 - (0.168736 * R) - (0.331264 * G) + (0.5      * B)
#    Cr = 128 + (0.5      * R) - (0.418688 * G) - (0.081312 * B)    
#    return Y, Cb, Cr
#
#def ycbcr_to_rgb(Y, Cb, Cr):
#    img = numpy.zeros((Y.shape[0], Y.shape[1], 3), dtype=float)
#    Cr -= 128
#    Cb -= 128
#    img[:,:,0] = Y +                  1.402 * Cr
#    img[:,:,1] = Y - 0.34414 * Cb - 0.71414 * Cr
#    img[:,:,2] = Y + 1.772 * Cb
#    return img


class Watermarker(object):
    def __init__(self, max_payload, ec_bytes, seed = 1895746671, mother = "bior3.1", sparsity = 0.7):
        self.mother = mother
        self.sparsity = sparsity
        self.rscodec = RSCodec(ec_bytes)
        self.max_payload = max_payload
        self.total_bits = (max_payload + ec_bytes) * 8
        self.seed = seed
    
#    def _interleave(self, cH, cV, cD):
#        vec = numpy.zeros(cH.size + cV.size + cD.size)
#        rcH = cH.ravel()
#        lH = cH.size
#        rcV = cV.ravel()
#        lV = cH.size + cV.size
#        rcD = cD.ravel()
#        
#        rand = Random(self.seed)
#        indexes = range(vec.size)
#        rand.shuffle(indexes)
#        for i, j in enumerate(indexes):
#            vec[i] = rcD[j - lV] if j >= lV else (rcV[j - lH] if j >= lH else rcH[j])
#        return vec
#    
#    def _deinterleave(self, vec, cH, cV, cD):
#        cH2 = numpy.zeros(cH.shape)
#        rcH = cH2.ravel()
#        lH = cH.size
#        cV2 = numpy.zeros(cV.shape)
#        rcV = cV2.ravel()
#        lV = cH.size + cV.size
#        cD2 = numpy.zeros(cD.shape)
#        rcD = cD2.ravel()
#        
#        rand = Random(self.seed)
#        indexes = range(vec.size)
#        rand.shuffle(indexes)
#        for i, v in enumerate(vec):
#            j = indexes[i]
#            if j >= lV:
#                rcD[j -lV] = v
#            elif j >= lH:
#                rcV[j - lH] = v
#            else:
#                rcH[j] = v
#        return cH2, cV2, cD2

    @classmethod
    def _interleave(cls, cH, cV, cD):
        vec = numpy.zeros(cH.size + cV.size + cD.size, dtype = float)
        vec[0::3] = cH.ravel()
        vec[1::3] = cV.ravel()
        vec[2::3] = cD.ravel()
        return vec
    
    @classmethod
    def _deinterleave(cls, vec, cH, cV, cD):
        return vec[0::3].reshape(cH.shape), vec[1::3].reshape(cV.shape), vec[2::3].reshape(cD.shape)
    
    def _generate_sequences(self, chunk_size):
        rand = Random(self.seed)
        seq0 = numpy.array([int(rand.random() >= self.sparsity) for _ in range(chunk_size)])
        seq1 = seq0[::-1]
        return seq0, seq1
    
    def _embed(self, img, payload, k):
        cA, (cH, cV, cD) = dwt2(img.astype(float), self.mother)
        vec = self._interleave(cH, cV, cD)
        chunk_size = vec.size // self.total_bits
        sequences = self._generate_sequences(chunk_size)
        
        for i, bit in enumerate(iterbits(payload)):
            offset = i * chunk_size
            vec[offset : offset + chunk_size] += k * sequences[bit]
            #vec[i : self.total_bits*chunk_size : self.total_bits] += k * sequences[bit]
        
        w, h = img.shape
        cH2, cV2, cD2 = self._deinterleave(vec, cH, cV, cD)
        return idwt2((cA, (cH2, cV2, cD2)), self.mother)[:w,:h]
    
    def embed(self, img, payload, k = 4, rescale_color = True):
        if len(payload) > self.max_payload:
            raise ValueError("payload too long")
        padded = bytearray(payload) + b"\x00" * (self.max_payload - len(payload))
        encoded = self.rscodec.encode(padded)
        
        if img.ndim == 2:
            output = self._embed(img, encoded, k)
        elif img.ndim == 3:
            output = numpy.zeros(img.shape, dtype=float)
            for i in range(img.shape[2]):
                output[:,:,i] = self._embed(img[:,:,i], encoded, k)
            #y, cb, cr = rgb_to_ycbcr(img)
            #y2 = self._embed(y, encoded, k)
            #cb = self._embed(cb, encoded, k)
            #cr = self._embed(cr, encoded, k)
            #y2 = rescale_intensity(y2, out_range = (numpy.min(y), numpy.max(y)))
            #Cb2 = rescale_intensity(Cb2, out_range = (numpy.min(Cb), numpy.max(Cb)))
            #Cr2 = rescale_intensity(Cr2, out_range = (numpy.min(Cr), numpy.max(Cr)))
            #output = ycbcr_to_rgb(y2, cb, cr)
        else:
            raise TypeError("img must be a 2d or 3d array")
        
        if rescale_color:
            output = rescale_intensity(output, out_range = (numpy.min(img), numpy.max(img)))
        #return toimage(output,cmin=0,cmax=255)
        return output
    
    def _extract(self, img):
        cA, (cH, cV, cD) = dwt2(img.astype(float), self.mother)
        vec = self._interleave(cH, cV, cD)
        chunk_size = vec.size // self.total_bits
        seq0, seq1 = self._generate_sequences(chunk_size)

        byte = 0
        output = bytearray()
        for i in range(self.total_bits):
            offset = i * chunk_size
            chunk = vec[offset: offset + chunk_size]
            #chunk = vec[i:self.total_bits*chunk_size:self.total_bits]
            corr0, _ = pearsonr(chunk, seq0)
            corr1, _ = pearsonr(chunk, seq1)
            bit = int(corr1 > corr0)
            byte = (byte << 1) | bit
            if i % 8 == 7:
                output.append(byte)
                byte = 0
        
        return output
    
    def _try_decode(self, payload):
        try:
            return self.rscodec.decode(payload)
        except ReedSolomonError:
            rpayload = bytearray(b ^ 255 for b in payload)
            return self.rscodec.decode(rpayload)
    
    def extract(self, img):
        if img.ndim == 2:
            return self._try_decode(self._extract(img))
        elif img.ndim == 3:
            for i in range(img.shape[2]):
                try:
                    return self._try_decode(self._extract(img[:,:,i]))
                except ReedSolomonError:
                    pass
            return self._try_decode(self._extract(mean(img, 2)))
        else:
            raise TypeError("img must be a 2d or 3d array")


