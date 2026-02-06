# planner/soundvision_parser.py

import re
import PyPDF2
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class SoundvisionParser:
    """Parser for L'Acoustics Soundvision PDF reports"""
    
    def __init__(self):
        self.raw_text = ""
        self.data = {
            'metadata': {},
            'arrays': []
        }
    
    def parse_pdf_file(self, pdf_file) -> Dict[str, Any]:
        """Main entry point to parse a PDF file"""
        try:
            # Extract text from PDF
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            self.raw_text = ""
            for page in pdf_reader.pages:
                self.raw_text += page.extract_text() + "\n"
            
            # Parse metadata
            self._parse_metadata()
            
            # Parse all arrays directly
            self._parse_all_arrays()
            
            return self.data
            
        except Exception as e:
            logger.error(f"Error parsing PDF: {str(e)}")
            raise
    
    def _parse_metadata(self):
        """Extract file metadata from header"""
        # Version
        version_match = re.search(r'Version:\s*([\d.]+)', self.raw_text)
        if version_match:
            self.data['metadata']['version'] = version_match.group(1)
        
        # Date
        date_match = re.search(r'Date:\s*(\d{4}/\d{2}/\d{2})', self.raw_text)
        if date_match:
            date_str = date_match.group(1)
            self.data['metadata']['date'] = datetime.strptime(date_str, '%Y/%m/%d').date().isoformat()
        
        # File name
        file_match = re.search(r'File name:\s*([^\n]+)', self.raw_text)
        if file_match:
            self.data['metadata']['file_name'] = file_match.group(1).strip()
        
        # Units
        self.data['metadata']['distance_unit'] = 'ft.in'
        self.data['metadata']['weight_unit'] = 'lb'
    
    def _parse_all_arrays(self):
        """Parse all arrays in the document, regardless of groups"""
        # Capture full group name including spaces (e.g., "KARA Mains", "KIVA Out", "X8 Outfill")
        group_pattern = r'\d+\.\s*Group:\s*([^\n]+?)(?:\n|$)'
        group_matches = list(re.finditer(group_pattern, self.raw_text))
        
        # Find all sources
        source_pattern = r'\d+\.\s*Source:\s*([^\n]+)'
        source_matches = list(re.finditer(source_pattern, self.raw_text))
        
        for source_match in source_matches:
            source_name = source_match.group(1).strip()
            source_pos = source_match.start()
            
            # Find which group this source belongs to
            group_context = "UNKNOWN"
            for i, group_match in enumerate(group_matches):
                group_pos = group_match.start()
                next_group_pos = group_matches[i+1].start() if i+1 < len(group_matches) else len(self.raw_text)
                
                if group_pos <= source_pos < next_group_pos:
                    group_context = group_match.group(1).strip()
                    break
            
            # Find the end of this source section
            next_source_pos = len(self.raw_text)
            for next_match in source_matches:
                if next_match.start() > source_pos:
                    next_source_pos = next_match.start()
                    break
            
            # Also check for next group boundary
            for group_match in group_matches:
                if group_match.start() > source_pos and group_match.start() < next_source_pos:
                    next_source_pos = group_match.start()
                    break
            
            source_text = self.raw_text[source_pos:next_source_pos]
            
            # Parse the source details
            array_data = self._parse_source_details(source_name, source_text, group_context)
            self.data['arrays'].append(array_data)
    
    def _parse_source_details(self, name: str, text: str, group_context: str) -> Dict[str, Any]:
        """Parse details of a single source/array"""
        # Parse the array name to get base name and symmetry
        parts = name.split('_')
        base_name = parts[0].strip()
        symmetry = '_'.join(parts[1:]).strip() if len(parts) > 1 else ''
        
        data = {
            'source_name': name,
            'array_base_name': base_name,
            'symmetry_type': symmetry,
            'group_context': group_context,
            'configuration': '',
            'bumper': '',
            'motors': 1,
            'position': {},
            'angles': {},
            'weight': {},
            'dimensions': {},
            'pickup_positions': {},
            'cabinets': []
        }
        
        # Configuration
        config_match = re.search(r'Configuration:\s*([^\n]+)', text)
        if config_match:
            data['configuration'] = config_match.group(1).strip()
        
        # Bumper
        bumper_match = re.search(r'Bumper:\s*([^\n]+)', text)
        if bumper_match:
            data['bumper'] = bumper_match.group(1).strip()

        # Extract MBAR hole A/B from bumper text for KARA
        bumper_text = data['bumper'].lower()
        if 'hole a' in bumper_text:
            data['mbar_hole'] = 'A'
        elif 'hole b' in bumper_text:
            data['mbar_hole'] = 'B'
        
        # Number of motors
        motors_match = re.search(r'#\s*motors:\s*(\d+)', text)
        if motors_match:
            data['motors'] = int(motors_match.group(1))
        
        # Position (X, Y, Z)
        pos_match = re.search(r'Position\s*\(X;\s*Y;\s*Z[^)]*\):\s*([-\d.]+);\s*([-\d.]+);\s*([-\d.]+)', text)
        if pos_match:
            data['position'] = {
                'x': float(pos_match.group(1)),
                'y': float(pos_match.group(2)),
                'z': float(pos_match.group(3))
            }
        
        # Site and Azimuth angles
        site_match = re.search(r'Site:\s*([-\d.]+)\s*°', text)
        if site_match:
            data['angles']['site'] = float(site_match.group(1))
        
        azimuth_match = re.search(r'Azimuth:\s*([-\d.]+)\s*°', text)
        if azimuth_match:
            data['angles']['azimuth'] = float(azimuth_match.group(1))
        
        # Top and bottom site angles
        top_site_match = re.search(r'Top site:\s*([-\d.]+)\s*°', text)
        if top_site_match:
            data['angles']['top_site'] = float(top_site_match.group(1))
        
        bottom_site_match = re.search(r'Bottom site:\s*([-\d.]+)\s*°', text)
        if bottom_site_match:
            data['angles']['bottom_site'] = float(bottom_site_match.group(1))
        
        # Weight information
        total_weight_match = re.search(r'Total weight[^:]*:\s*([\d.]+)\s*lb', text)
        if total_weight_match:
            data['weight']['total'] = float(total_weight_match.group(1))
        
        enclosure_weight_match = re.search(r'Total enclosure weight:\s*([\d.]+)\s*lb', text)
        if enclosure_weight_match:
            data['weight']['enclosure'] = float(enclosure_weight_match.group(1))
        
        # Motor loads
        front_motor_match = re.search(r'Front motor load:\s*([\d.]+)\s*lb', text)
        if front_motor_match:
            data['weight']['front_motor'] = float(front_motor_match.group(1))
        
        rear_motor_match = re.search(r'Rear motor load:\s*([\d.]+)\s*lb', text)
        if rear_motor_match:
            data['weight']['rear_motor'] = float(rear_motor_match.group(1))
        
        # Bottom elevation
        bottom_elev_match = re.search(r'Bottom elevation:\s*([\d.]+)', text)
        if bottom_elev_match:
            data['dimensions']['bottom_elevation'] = float(bottom_elev_match.group(1))
        
        # Pickup positions (for hole numbers and MBar)
        front_pickup_match = re.search(r'Front pickup position[^:]*:\s*(\d+)\s*\([^)]+\)', text)
        if front_pickup_match:
            hole_num = int(front_pickup_match.group(1))
            data['pickup_positions']['front'] = hole_num
            
        rear_pickup_match = re.search(r'Rear pickup position[^:]*:\s*(\d+)\s*\([^)]+\)', text)
        if rear_pickup_match:
            data['pickup_positions']['rear'] = int(rear_pickup_match.group(1))
        
        # Parse cabinet table
        data['cabinets'] = self._parse_cabinet_table(text)
        
        return data
    
    def _parse_cabinet_table(self, text: str) -> List[Dict[str, Any]]:
        """Parse the cabinet configuration table"""
        cabinets = []
        
        # Check if this is a Panflex table (KARA)
        has_panflex = 'Panflex' in text or bool(re.search(r'\d+/\d+', text))
        
        if has_panflex:
            # KARA style with Panflex - always has angle column
            # Format: #1 KARA II 5 -8.2 24.00 23.02 55/35
            pattern = r'#(\d+)\s+([A-Z]+(?:\s+[A-Z]+)*)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+(\d+/\d+)'
            matches = re.finditer(pattern, text)
            
            for match in matches:
                cabinet = {
                    'position': int(match.group(1)),
                    'model': match.group(2).strip(),
                    'angle': float(match.group(3)) if match.group(3) else 0,
                    'site': float(match.group(4)),
                    'top_z': float(match.group(5)),
                    'bottom_z': float(match.group(6)),
                    'panflex': match.group(7)
                }
                cabinets.append(cabinet)
            return cabinets
        
        # Non-Panflex format (KIVA, KS28, SYVA, X8, etc.)
        # Challenge: First row may have NO angle, subsequent rows have angle
        # Row 1: #1 KIVA II 0 32.10 32.03 (3 data numbers: site, top_z, bottom_z)
        # Row 2+: #2 KIVA II 0 0 32.03 31.08 (4 data numbers: angle, site, top_z, bottom_z)
        
        # Find all lines starting with # followed by a number
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            
            # Must start with # and a digit
            if not re.match(r'^#\d+', line):
                continue
            
            # Skip header rows
            if 'Type' in line and ('Angles' in line or 'Site' in line):
                continue
            
            # Extract all numbers from the line
            # Pattern: #position MODEL_NAME numbers...
            cabinet_match = re.match(r'^#(\d+)\s+([A-Z]+(?:\s+[A-Z]+)*(?:\s+LOW)?)\s+(.*)', line)
            if not cabinet_match:
                continue
            
            position = int(cabinet_match.group(1))
            model = cabinet_match.group(2).strip()
            rest = cabinet_match.group(3).strip()
            
            # Extract numbers from the rest of the line
            numbers = re.findall(r'[-]?\d+\.?\d*', rest)
            
            if len(numbers) >= 4:
                # Has angle: angle, site, top_z, bottom_z
                cabinet = {
                    'position': position,
                    'model': model,
                    'angle': float(numbers[0]),
                    'site': float(numbers[1]),
                    'top_z': float(numbers[2]),
                    'bottom_z': float(numbers[3])
                }
                cabinets.append(cabinet)
            elif len(numbers) == 3:
                # No angle (first cabinet): site, top_z, bottom_z
                cabinet = {
                    'position': position,
                    'model': model,
                    'angle': 0,  # First cabinet has no inter-cabinet angle
                    'site': float(numbers[0]),
                    'top_z': float(numbers[1]),
                    'bottom_z': float(numbers[2])
                }
                cabinets.append(cabinet)
        
        return cabinets


def import_soundvision_prediction(prediction_obj, pdf_file):
    """Import a Soundvision PDF and create database objects"""
    from .models import SpeakerArray, SpeakerCabinet
    
    # Clear existing arrays and cabinets for this prediction
    prediction_obj.speaker_arrays.all().delete()  # This will cascade delete cabinets too
    
    parser = SoundvisionParser()
    data = parser.parse_pdf_file(pdf_file)
    
    # Store raw parsed data
    prediction_obj.raw_data = data
    
    # Update metadata
    if 'metadata' in data:
        meta = data['metadata']
        if 'version' in meta:
            prediction_obj.version = meta['version']
        if 'date' in meta:
            prediction_obj.date_generated = datetime.fromisoformat(meta['date']).date()
        if 'file_name' in meta and not prediction_obj.file_name:
            prediction_obj.file_name = meta['file_name']
    
    prediction_obj.save()
    
    # Create arrays
    for array_data in data.get('arrays', []):
        # Determine configuration type
        config = array_data.get('configuration', '').lower()
        if 'vertical' in config and 'flown' in config:
            config_type = 'vertical_flown'
        elif 'vertical' in config and 'ground' in config:
            config_type = 'vertical_ground'
        elif 'horizontal' in config:
            config_type = 'horizontal'
        else:
            config_type = 'vertical_flown'  # default
        
        # Determine bumper type
        bumper = array_data.get('bumper', '').upper()
        bumper_type = 'NONE'
        for bt in ['KIBU-SB', 'KIBU II', 'M-BUMP', 'K1-BUMP', 'K2-BUMP', 'A-BUMP', 'SYVA BASE']:
            if bt in bumper:
                bumper_type = bt
                break
        
        # Create array
        array = SpeakerArray.objects.create(
            prediction=prediction_obj,
            source_name=array_data['source_name'],
            array_base_name=array_data['array_base_name'],
            symmetry_type=array_data.get('symmetry_type', ''),
            group_context=array_data.get('group_context', ''),
            configuration=config_type,
            bumper_type=bumper_type,
            num_motors=array_data.get('motors', 1),
            is_single_point=(array_data.get('motors', 1) == 1),
            
            # Position
            position_x=Decimal(str(array_data['position'].get('x', 0))) if 'position' in array_data else None,
            position_y=Decimal(str(array_data['position'].get('y', 0))) if 'position' in array_data else None,
            position_z=Decimal(str(array_data['position'].get('z', 0))) if 'position' in array_data else None,
            
            # Angles
            site_angle=Decimal(str(array_data['angles'].get('site', 0))) if 'angles' in array_data else None,
            azimuth=Decimal(str(array_data['angles'].get('azimuth', 0))) if 'angles' in array_data else None,
            top_site=Decimal(str(array_data['angles'].get('top_site', 0))) if 'angles' in array_data else None,
            bottom_site=Decimal(str(array_data['angles'].get('bottom_site', 0))) if 'angles' in array_data else None,
            
            # Weight
            total_weight_lb=Decimal(str(array_data['weight'].get('total', 0))) if 'weight' in array_data else None,
            enclosure_weight_lb=Decimal(str(array_data['weight'].get('enclosure', 0))) if 'weight' in array_data else None,
            front_motor_load_lb=Decimal(str(array_data['weight'].get('front_motor', 0))) if 'weight' in array_data else None,
            rear_motor_load_lb=Decimal(str(array_data['weight'].get('rear_motor', 0))) if 'weight' in array_data else None,
            
            # Dimensions
            bottom_elevation=Decimal(str(array_data['dimensions'].get('bottom_elevation', 0))) if 'dimensions' in array_data else None,
            
            # MBar hole for KARA
            mbar_hole=array_data.get('mbar_hole', '')
        )
        
        # Set pickup positions if available
        if 'pickup_positions' in array_data:
            if 'front' in array_data['pickup_positions']:
                array.front_pickup_position = str(array_data['pickup_positions']['front'])
            if 'rear' in array_data['pickup_positions']:
                array.rear_pickup_position = str(array_data['pickup_positions']['rear'])
        
        # Calculate bumper angle for dual-point
        if array.num_motors == 2:
            array.calculate_bumper_angle()
        
        array.save()
        
        # Create cabinets
        for i, cab_data in enumerate(array_data.get('cabinets', [])):
            cabinet = SpeakerCabinet.objects.create(
                array=array,
                position_number=cab_data.get('position', i + 1),
                speaker_model=cab_data['model'],
                angle_to_next=Decimal(str(cab_data.get('angle', 0))),
                site_angle=Decimal(str(cab_data.get('site', 0))),
                top_z=Decimal(str(cab_data.get('top_z', 0))),
                bottom_z=Decimal(str(cab_data.get('bottom_z', 0))),
                panflex_setting=cab_data.get('panflex', '')
            )
    
    return prediction_obj