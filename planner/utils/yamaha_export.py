# planner/utils/yamaha_export.py
from io import StringIO, BytesIO
from django.http import HttpResponse
import zipfile


def export_yamaha_csvs(console):
    """Export all Yamaha Rivage CSV files"""
    zip_buffer = BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Name files
        zip_file.writestr('InName.csv', generate_input_csv(console))
        zip_file.writestr('MixName.csv', generate_mix_csv(console))
        zip_file.writestr('MtxName.csv', generate_matrix_csv(console))
        zip_file.writestr('StName.csv', generate_stereo_csv(console))
        zip_file.writestr('MuteDCAName.csv', generate_mute_dca_csv(console))
        
        # Patch files
        zip_file.writestr('InPatch.csv', generate_in_patch_csv(console))
        zip_file.writestr('InInsPatch.csv', generate_in_ins_patch_csv())
        zip_file.writestr('OutInsPatch.csv', generate_out_ins_patch_csv())
        zip_file.writestr('PortRackPatch.csv', generate_port_rack_patch_csv())
        zip_file.writestr('RecordingPatch.csv', generate_recording_patch_csv())
        zip_file.writestr('SubInPatch.csv', generate_sub_in_patch_csv())
    
    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.read(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{console.name}_Yamaha_Rivage.zip"'
    return response


def generate_input_csv(console):
    """Generate InName.csv - 288 inputs"""
    output = StringIO()
    
    output.write('[Information]\n')
    output.write('CS-R3\n')
    output.write('DSP-RX\n')
    output.write('V6.60\n')
    output.write('[InName]\n')
    output.write('IN,NAME,COLOR,ICON,\n')
    
    # Get existing inputs as dict
    inputs_dict = {}
    for inp in console.consoleinput_set.all():
        try:
            ch_num = int(inp.input_ch)
            inputs_dict[ch_num] = inp
        except (ValueError, TypeError):
            pass
    
    # Generate ALL 288 inputs
    for i in range(1, 289):
        input_num = f"_{i:03d}"
        
        if i in inputs_dict and inputs_dict[i].source:
            name = inputs_dict[i].source.replace(',', ';')
        else:
            name = f"ch{i}"
        
        output.write(f'{input_num},{name},Blue,Dynamic,\n')
    
    return output.getvalue()


def generate_mix_csv(console):
    """Generate MixName.csv - 72 mixes (2-digit padding)"""
    output = StringIO()
    
    output.write('[Information]\n')
    output.write('CS-R3\n')
    output.write('DSP-RX\n')
    output.write('V6.60\n')
    output.write('[MixName]\n')
    output.write('MIX,NAME,COLOR,ICON,\n')
    
    auxes_dict = {}
    for aux in console.consoleauxoutput_set.all():
        try:
            aux_num = int(aux.aux_number)
            auxes_dict[aux_num] = aux
        except (ValueError, TypeError):
            pass
    
    # Generate ALL 72 mixes with 2-digit padding
    for i in range(1, 73):
        mix_num = f"_{i:02d}"  # 2-digit!
        
        if i in auxes_dict and auxes_dict[i].name:
            name = auxes_dict[i].name.replace(',', ';')
        else:
            name = f"MX{i}"
        
        output.write(f'{mix_num},{name},Orange,Blank,\n')  # Orange color
    
    return output.getvalue()


def generate_matrix_csv(console):
    """Generate MtxName.csv - 36 matrices (2-digit padding)"""
    output = StringIO()
    
    output.write('[Information]\n')
    output.write('CS-R3\n')
    output.write('DSP-RX\n')
    output.write('V6.60\n')
    output.write('[MtxName]\n')
    output.write('MATRIX,NAME,COLOR,ICON,\n')
    
    matrices_dict = {}
    for mtx in console.consolematrixoutput_set.all():
        try:
            mtx_num = int(mtx.matrix_number)
            matrices_dict[mtx_num] = mtx
        except (ValueError, TypeError):
            pass
    
    # Generate ALL 36 matrices with 2-digit padding
    for i in range(1, 37):
        matrix_num = f"_{i:02d}"  # 2-digit!
        
        if i in matrices_dict and matrices_dict[i].name:
            name = matrices_dict[i].name.replace(',', ';')
        else:
            name = f"MT{i}"
        
        output.write(f'{matrix_num},{name},Orange,Blank,\n')  # Orange color
    
    return output.getvalue()


def generate_stereo_csv(console):
    """Generate StName.csv - 4 stereo channels"""
    output = StringIO()
    
    output.write('[Information]\n')
    output.write('CS-R3\n')
    output.write('DSP-RX\n')
    output.write('V6.60\n')
    output.write('[StName]\n')
    output.write('STEREO,NAME,COLOR,ICON,\n')
    
    # Map to Rivage format
    stereo_map = {
        'L': '_AL',
        'R': '_AR',
        'M': '_BL',  # Map Mono to Stereo B Left
    }
    
    stereo_dict = {}
    for stereo in console.consolestereooutput_set.all():
        stereo_dict[stereo.stereo_type] = stereo.name or stereo.get_stereo_type_display()
    
    # Generate all 4 Rivage channels (even though we only use 3)
    for rivage_type, rivage_code in [('_AL', 'L'), ('_AR', 'R'), ('_BL', 'M'), ('_BR', 'M')]:
        name = stereo_dict.get(rivage_code, 'ST A' if rivage_type.startswith('_A') else 'ST B')
        output.write(f'{rivage_type},{name},Orange,Blank,\n')
    
    return output.getvalue()


def generate_mute_dca_csv(console):
    """Generate MuteDCAName.csv - DCAs + Mutes"""
    output = StringIO()
    
    output.write('[Information]\n')
    output.write('CS-R3\n')
    output.write('DSP-RX\n')
    output.write('V6.60\n')
    output.write('[MuteDCAName]\n')
    output.write('DCA,NAME,COLOR,ICON,\n')
    
    # 24 DCAs
    for i in range(1, 25):
        output.write(f'DCA {i},DCA{i},Yellow,Blank,\n')
    
    # 12 Mutes with triple commas
    for i in range(1, 13):
        output.write(f'Mute {i},Mute{i},,,\n')  # Triple commas!
    
    return output.getvalue()


def generate_in_patch_csv(console):
    """Generate InPatch.csv - input routing"""
    output = StringIO()
    
    output.write('[Information]\n')
    output.write('CS-R3\n')
    output.write('DSP-RX\n')
    output.write('V6.60\n')
    output.write('[InPatch]\n')
    output.write('IN_PATCH,SOURCE,COMMENT\n')
    
    # Generate minimal patch for all 288 channels (A and B)
    for i in range(1, 289):
        # Channel A
        output.write(f'CH {i} A,NONE,# Blank,\n')
        # Channel B
        output.write(f'CH {i} B,NONE,# Blank,\n')
    
    return output.getvalue()


def generate_in_ins_patch_csv():
    """Generate InInsPatch.csv - minimal placeholder"""
    output = StringIO()
    
    output.write('[Information]\n')
    output.write('CS-R3\n')
    output.write('DSP-RX\n')
    output.write('V6.60\n')
    output.write('[InInsPatch]\n')
    output.write('IN_INS_PATCH,->A,A->,->B,B->,->C,C->,->D,D->,\n')
    
    # Minimal entry
    for i in range(1, 289):
        output.write(f'CH {i} INS1 ,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE,\n')
        output.write(f'CH {i} INS2 ,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE,\n')
    
    return output.getvalue()


def generate_out_ins_patch_csv():
    """Generate OutInsPatch.csv"""
    output = StringIO()
    
    output.write('[Information]\n')
    output.write('CS-R3\n')
    output.write('DSP-RX\n')
    output.write('V6.60\n')
    output.write('[OutInsPatch]\n')
    output.write('OUT_INS_PATCH,->A,A->,->B,B->,->C,C->,->D,D->,\n')
    
    # Mix channels
    for i in range(1, 73):
        output.write(f'MIX {i} INS1 ,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE,\n')
        output.write(f'MIX {i} INS2 ,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE,\n')
    
    # Matrix channels
    for i in range(1, 37):
        output.write(f'MATRIX {i} INS1 ,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE,\n')
        output.write(f'MATRIX {i} INS2 ,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE,\n')
    
    return output.getvalue()


def generate_port_rack_patch_csv():
    """Generate PortRackPatch.csv"""
    output = StringIO()
    
    output.write('[Information]\n')
    output.write('CS-R3\n')
    output.write('DSP-RX\n')
    output.write('V6.60\n')
    output.write('[PortRackPatch]\n')
    output.write('PortRack_PATCH,SOURCE,COMMENT\n')
    
    # Minimal slot entries
    for slot in ['CS1', 'CS2']:
        for i in range(1, 9):
            output.write(f'{slot} OMNI {i},NONE,# Blank,\n')
        for i in range(1, 9):
            output.write(f'{slot} AES/EBU {i},NONE,# Blank,\n')
        for i in range(1, 17):
            output.write(f'{slot} MY SLOT1 {i},NONE,# Blank,\n')
            output.write(f'{slot} MY SLOT2 {i},NONE,# Blank,\n')
    
    return output.getvalue()


def generate_recording_patch_csv():
    """Generate RecordingPatch.csv"""
    output = StringIO()
    
    output.write('[Information]\n')
    output.write('CS-R3\n')
    output.write('DSP-RX\n')
    output.write('V6.60\n')
    output.write('[RecordingPatch]\n')
    output.write('RECORDING_PATCH,SOURCE,COMMENT\n')
    
    # 32 recording channels
    for i in range(1, 33):
        output.write(f'RECORDING {i},NONE,# Blank,\n')
    
    return output.getvalue()


def generate_sub_in_patch_csv():
    """Generate SubInPatch.csv"""
    output = StringIO()
    
    output.write('[Information]\n')
    output.write('CS-R3\n')
    output.write('DSP-RX\n')
    output.write('V6.60\n')
    output.write('[SubInPatch]\n')
    output.write('SUB_IN_PATCH,SOURCE,COMMENT\n')
    
    # 4 sub inputs
    for i in range(1, 5):
        output.write(f'SUB IN {i},NONE,# Blank,\n')
    
    return output.getvalue()