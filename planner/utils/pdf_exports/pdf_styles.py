# planner/utils/pdf_exports/pdf_styles.py
"""
Shared PDF styling system for Audio Patch exports
Provides consistent formatting across all module PDFs
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import TableStyle
from datetime import datetime

# Page settings
PORTRAIT_PAGE = letter
LANDSCAPE_PAGE = landscape(letter)
MARGIN = 0.5 * inch

# Brand colors (print-friendly with blue accent)
BRAND_BLUE = colors.HexColor('#4a9eff')
DARK_GRAY = colors.HexColor('#333333')
MEDIUM_GRAY = colors.HexColor('#666666')
LIGHT_GRAY = colors.HexColor('#cccccc')
BACKGROUND_GRAY = colors.HexColor('#f5f5f5')

class PDFStyles:
    """Centralized styling for all PDF exports"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._create_custom_styles()
    
    def _create_custom_styles(self):
        """Define custom paragraph styles"""
        
        # Main header style
        self.styles.add(ParagraphStyle(
            name='CustomHeader',
            parent=self.styles['Heading1'],
            fontSize=18,
            textColor=BRAND_BLUE,
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        # Section header style
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=DARK_GRAY,
            spaceBefore=12,
            spaceAfter=8,
            fontName='Helvetica-Bold'
        ))
        
        # Subsection header
        self.styles.add(ParagraphStyle(
            name='SubsectionHeader',
            parent=self.styles['Heading3'],
            fontSize=12,
            textColor=DARK_GRAY,
            spaceBefore=8,
            spaceAfter=6,
            fontName='Helvetica-Bold'
        ))
        
        # Body text
        self.styles.add(ParagraphStyle(
            name='CustomBody',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=DARK_GRAY,
            spaceAfter=6,
            fontName='Helvetica'
        ))
        
        # Small text (for footnotes, timestamps)
        self.styles.add(ParagraphStyle(
            name='SmallText',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=MEDIUM_GRAY,
            fontName='Helvetica'
        ))
    
    def get_header_style(self):
        """Get main header style"""
        return self.styles['CustomHeader']
    
    def get_section_style(self):
        """Get section header style"""
        return self.styles['SectionHeader']
    
    def get_subsection_style(self):
        """Get subsection header style"""
        return self.styles['SubsectionHeader']
    
    def get_body_style(self):
        """Get body text style"""
        return self.styles['CustomBody']
    
    def get_small_style(self):
        """Get small text style"""
        return self.styles['SmallText']
    
    @staticmethod
    def get_table_style(header_color=BRAND_BLUE, grid_color=LIGHT_GRAY):
        """
        Get standard table style with blue header
        
        Args:
            header_color: Color for header row (default: brand blue)
            grid_color: Color for grid lines (default: light gray)
        
        Returns:
            TableStyle object
        """
        return TableStyle([
            # Header row styling
            ('BACKGROUND', (0, 0), (-1, 0), header_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            
            # Data rows styling
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 1), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 1), (-1, -1), 6),
            ('RIGHTPADDING', (0, 1), (-1, -1), 6),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            
            # Alternating row colors for readability
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BACKGROUND_GRAY]),
            
            # Grid lines
            ('GRID', (0, 0), (-1, -1), 0.5, grid_color),
            ('LINEBELOW', (0, 0), (-1, 0), 2, header_color),
        ])
    
    @staticmethod
    def get_compact_table_style():
        """Get table style for dense data (smaller padding)"""
        style = PDFStyles.get_table_style()
        style.add('TOPPADDING', (0, 1), (-1, -1), 2)
        style.add('BOTTOMPADDING', (0, 1), (-1, -1), 2)
        return style
    
    @staticmethod
    def calculate_column_widths(page_width, num_columns, min_width=0.5*inch):
        """
        Calculate optimal column widths for tables
        
        Args:
            page_width: Available width for table
            num_columns: Number of columns
            min_width: Minimum width per column
        
        Returns:
            List of column widths
        """
        available_width = page_width - (2 * MARGIN)
        width_per_column = max(available_width / num_columns, min_width)
        return [width_per_column] * num_columns
    
    @staticmethod
    def format_header_text(show_name=None, document_type="Show Report", console_name=None):
        """
        Format header text with consistent styling
        
        Args:
            show_name: Name of the show/event
            document_type: Type of document (e.g., "Console Configuration")
            console_name: Optional console/device name
        
        Returns:
            Formatted header string
        """
        parts = []
        if show_name:
            parts.append(f"<b>{show_name}</b>")
        if document_type:
            parts.append(document_type)
        if console_name:
            parts.append(f"({console_name})")
        
        return " - ".join(parts) if parts else document_type
    
    @staticmethod
    def add_page_number(canvas, doc):
        """
        Add page numbers to footer (use as onPage callback)
        
        Args:
            canvas: ReportLab canvas object
            doc: Document template
        """
        canvas.saveState()
        
        # Page number
        page_num = canvas.getPageNumber()
        text = f"Page {page_num}"
        
        # Draw at bottom center
        canvas.setFont('Helvetica', 8)
        canvas.setFillColorRGB(0.4, 0.4, 0.4)
        canvas.drawCentredString(
            doc.pagesize[0] / 2,
            0.3 * inch,
            text
        )
        
        # Add generation timestamp in bottom right
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        canvas.drawRightString(
            doc.pagesize[0] - MARGIN,
            0.3 * inch,
            f"Generated: {timestamp}"
        )
        
        canvas.restoreState()
    
    @staticmethod
    def create_section_divider():
        """Create a visual section divider"""
        from reportlab.platypus import Spacer, HRFlowable
        return [
            Spacer(1, 0.1 * inch),
            HRFlowable(width="100%", thickness=1, color=LIGHT_GRAY, spaceAfter=0.1*inch),
        ]
