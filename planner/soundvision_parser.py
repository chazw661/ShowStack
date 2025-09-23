# Create file: planner/soundvision_parser.py

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
            'arrays': []  # Changed from 'groups' to 'arrays'
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
            
            # Parse all arrays directly (ignore groups)
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
        # First, find group context for each array
        group_pattern = r'\d+\.\s*Group:\s*(\w+)'
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
                    group_context = group_match.group(1)
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
        # Front pickup: "1 (29.03; 8.09; 24.03)" or "0 (0.00; 17.09; 24.02)"
        front_pickup_match = re.search(r'Front pickup position[^:]*:\s*(\d+)\s*\([^)]+\)', text)
        if front_pickup_match:
            hole_num = int(front_pickup_match.group(1))
            data['pickup_positions']['front'] = hole_num
            
            # For KARA, determine MBar A or B based on hole number
            if 'KARA' in base_name.upper():
                # Hole 0 = MBar A, Hole 2 = MBar B (typical)
                if hole_num == 0:
                    data['mbar_hole'] = 'A'
                elif hole_num == 2:
                    data['mbar_hole'] = 'B'
        
        rear_pickup_match = re.search(r'Rear pickup position[^:]*:\s*(\d+)\s*\([^)]+\)', text)
        if rear_pickup_match:
            data['pickup_positions']['rear'] = int(rear_pickup_match.group(1))
        
        # Parse cabinet table
        data['cabinets'] = self._parse_cabinet_table(text)
        
        return data
    
    def _parse_cabinet_table(self, text: str) -> List[Dict[str, Any]]:
        """Parse the cabinet configuration table"""
        cabinets = []
        
        # Pattern for table rows with or without Panflex
        # Matches lines like: "#1 KIVA II -13.2 24.00 23.05"
        # or: "#1 KARA II 5 -8.2 24.00 23.02 55/35"
        
        # Try to find the table header to understand format
        has_panflex = 'Panflex' in text or bool(re.search(r'\d+/\d+', text))
        
        if has_panflex:
            # KARA style with Panflex
            pattern = r'#(\d+)\s+([A-Z]+(?:\s+[A-Z]+)*)\s+([-\d.]+)?\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+(\d+/\d+)'
            matches = re.finditer(pattern, text)
            
            for match in matches:
                cabinet = {
                    'position': int(match.group(1)),
                    'model': match.group(2).strip(),
                    'angle': float(match.group(3)) if match.group(3) and match.group(3) != '' else 0,
                    'site': float(match.group(4)),
                    'top_z': float(match.group(5)),
                    'bottom_z': float(match.group(6)),
                    'panflex': match.group(7)
                }
                cabinets.append(cabinet)
        
        # If no KARA matches or not KARA, try standard format
        if not cabinets:
            # Standard format without Panflex
            pattern = r'#(\d+)\s+([A-Z]+(?:\s+[A-Z]+)*)\s+([-\d.]+)?\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)'
            matches = re.finditer(pattern, text)
            
            for match in matches:
                angle_str = match.group(3)
                # Handle empty angle field
                angle = 0
                if angle_str and angle_str.strip() and angle_str != '':
                    try:
                        angle = float(angle_str)
                    except:
                        angle = 0
                
                cabinet = {
                    'position': int(match.group(1)),
                    'model': match.group(2).strip(),
                    'angle': angle,
                    'site': float(match.group(4)),
                    'top_z': float(match.group(5)),
                    'bottom_z': float(match.group(6))
                }
                cabinets.append(cabinet)
        
        return cabinets


def import_soundvision_prediction(prediction_obj, pdf_file):
    """Import a Soundvision PDF and create database objects"""
    from .models import SpeakerArray, SpeakerCabinet
    
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
        else:
            config_type = 'vertical_flown'  # default
        
        # Determine bumper type
        bumper = array_data.get('bumper', '').upper()
        bumper_type = 'NONE'
        for bt in ['KIBU-SB', 'KIBU II', 'M-BUMP', 'K1-BUMP', 'K2-BUMP', 'A-BUMP']:
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
        for cab_data in array_data.get('cabinets', []):
            cabinet = SpeakerCabinet.objects.create(
                array=array,
                position_number=cab_data['position'],
                speaker_model=cab_data['model'],
                angle_to_next=Decimal(str(cab_data.get('angle', 0))),
                site_angle=Decimal(str(cab_data.get('site', 0))),
                top_z=Decimal(str(cab_data.get('top_z', 0))),
                bottom_z=Decimal(str(cab_data.get('bottom_z', 0))),
                panflex_setting=cab_data.get('panflex', '')
            )
    
    return prediction_obj