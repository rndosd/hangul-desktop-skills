"""Measure U+0020 advance from an existing local SFNT font; no installs/registry.

This is a nominal font metric, never evidence of a Hancom rendered position.
"""
import hashlib,struct,math
from pathlib import Path
from functools import lru_cache

FONT_FILES={
 '맑은 고딕':('malgun.ttf','malgunbd.ttf'),
 '함초롬바탕':('HANBatang.TTF','HANBatangB.TTF'),
 '함초롬돋움':('HANDotum.TTF','HANDotumB.TTF'),
 'Arial':('arial.ttf','arialbd.ttf'),
}

@lru_cache(maxsize=32)
def space_metric(font,bold=False):
    if font not in FONT_FILES:
        raise ValueError('자동 공백 들여쓰기를 측정할 로컬 글꼴 경로가 없습니다. 사용자 지정 heading_layout과 항목 indent_left_mm를 명시하거나 지원 글꼴을 선택하세요.')
    path=Path('C:/Windows/Fonts')/FONT_FILES[font][1 if bold else 0]
    data=path.read_bytes()
    if data[:4] not in (b'\x00\x01\x00\x00',b'OTTO'):raise ValueError('Unsupported SFNT font')
    count=struct.unpack_from('>H',data,4)[0];tables={}
    for i in range(count):
        tag,_,off,length=struct.unpack_from('>4sIII',data,12+16*i)
        if off+length>len(data):raise ValueError('Invalid font table bounds')
        tables[tag.decode()]=(off,length)
    units=struct.unpack_from('>H',data,tables['head'][0]+18)[0]
    metrics=struct.unpack_from('>H',data,tables['hhea'][0]+34)[0]
    cmap=tables['cmap'][0];count=struct.unpack_from('>H',data,cmap+2)[0];glyph=None
    for i in range(count):
        platform,encoding,offset=struct.unpack_from('>HHI',data,cmap+4+8*i);base=cmap+offset
        if platform not in (0,3) or struct.unpack_from('>H',data,base)[0]!=4:continue
        segments=struct.unpack_from('>H',data,base+6)[0]//2
        ends=base+14;starts=ends+2*segments+2;deltas=starts+2*segments;ranges=deltas+2*segments
        for j in range(segments):
            start=struct.unpack_from('>H',data,starts+2*j)[0];end=struct.unpack_from('>H',data,ends+2*j)[0]
            if not start<=32<=end:continue
            delta=struct.unpack_from('>h',data,deltas+2*j)[0];roff=struct.unpack_from('>H',data,ranges+2*j)[0]
            glyph=(32+delta)&65535 if roff==0 else struct.unpack_from('>H',data,ranges+2*j+roff+2*(32-start))[0]
            if roff and glyph:glyph=(glyph+delta)&65535
            break
        if glyph is not None:break
    if not glyph or not units or not metrics:raise ValueError('U+0020 glyph or metric unavailable')
    advance=struct.unpack_from('>H',data,tables['hmtx'][0]+4*min(glyph,metrics-1))[0]
    return dict(font=font,bold=bold,path=str(path),sha256=hashlib.sha256(data).hexdigest(),units_per_em=units,space_glyph_id=glyph,space_advance=advance)

def indent_mm(font,point,spaces,bold=False,ratio=100,letter_spacing=0):
    if letter_spacing!=0:raise ValueError('자간이 0이 아닌 경우 공백 폭 자동 측정을 보장하지 않습니다. 사용자 지정 들여쓰기를 명시하세요.')
    if spaces==0:return 0.0
    metric=space_metric(font,bold)
    return spaces*metric['space_advance']/metric['units_per_em']*point*ratio/100*25.4/72
