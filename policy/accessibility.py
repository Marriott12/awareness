"""Accessibility utilities for WCAG 2.1 AA compliance.

Provides utilities and helpers to ensure the application meets
Web Content Accessibility Guidelines (WCAG) 2.1 Level AA standards.
"""
from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def aria_label(text):
    """Add ARIA label attribute."""
    return format_html('aria-label="{}"', text)


@register.simple_tag
def aria_describedby(element_id):
    """Add ARIA describedby attribute."""
    return format_html('aria-describedby="{}"', element_id)


@register.simple_tag
def skip_to_content():
    """Render skip to main content link."""
    return format_html(
        '<a href="#main-content" class="skip-link">Skip to main content</a>'
    )


@register.simple_tag
def role(role_type):
    """Add ARIA role attribute."""
    return format_html('role="{}"', role_type)


@register.filter
def add_aria_current(value, current_page):
    """Add aria-current to navigation links."""
    if value == current_page:
        return mark_safe('aria-current="page"')
    return ''


@register.simple_tag
def sr_only(text):
    """Render screen reader only text."""
    return format_html('<span class="sr-only">{}</span>', text)


@register.simple_tag
def focus_indicator():
    """Add focus indicator for keyboard navigation."""
    return format_html('tabindex="0" class="focusable"')


# Color contrast checker
def check_color_contrast(foreground, background):
    """
    Check if color combination meets WCAG AA standards.
    
    Args:
        foreground: Foreground color hex code
        background: Background color hex code
    
    Returns:
        Dictionary with contrast ratio and compliance status
    """
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def relative_luminance(rgb):
        r, g, b = [x / 255.0 for x in rgb]
        r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
        g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
        b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    
    fg_lum = relative_luminance(hex_to_rgb(foreground))
    bg_lum = relative_luminance(hex_to_rgb(background))
    
    lighter = max(fg_lum, bg_lum)
    darker = min(fg_lum, bg_lum)
    
    contrast_ratio = (lighter + 0.05) / (darker + 0.05)
    
    return {
        'ratio': round(contrast_ratio, 2),
        'aa_normal': contrast_ratio >= 4.5,  # WCAG AA for normal text
        'aa_large': contrast_ratio >= 3.0,   # WCAG AA for large text
        'aaa_normal': contrast_ratio >= 7.0, # WCAG AAA for normal text
        'aaa_large': contrast_ratio >= 4.5,  # WCAG AAA for large text
    }


# Form field accessibility helpers
def make_form_accessible(form):
    """
    Add accessibility attributes to form fields.
    
    Args:
        form: Django form instance
    
    Returns:
        Modified form with accessibility attributes
    """
    for field_name, field in form.fields.items():
        # Add aria-label
        if field.label:
            field.widget.attrs['aria-label'] = field.label
        
        # Add aria-required for required fields
        if field.required:
            field.widget.attrs['aria-required'] = 'true'
        
        # Add aria-invalid for fields with errors
        if field_name in form.errors:
            field.widget.attrs['aria-invalid'] = 'true'
            field.widget.attrs['aria-describedby'] = f'{field_name}-error'
        
        # Add autocomplete attributes
        autocomplete_mapping = {
            'email': 'email',
            'username': 'username',
            'password': 'current-password',
            'first_name': 'given-name',
            'last_name': 'family-name',
        }
        if field_name in autocomplete_mapping:
            field.widget.attrs['autocomplete'] = autocomplete_mapping[field_name]
    
    return form


# Keyboard navigation support
KEYBOARD_SHORTCUTS = {
    'dashboard': 'Alt+D',
    'training': 'Alt+T',
    'quizzes': 'Alt+Q',
    'policies': 'Alt+P',
    'help': 'Alt+H',
    'logout': 'Alt+L',
}


def get_keyboard_shortcuts_json():
    """Get keyboard shortcuts as JSON for JavaScript."""
    import json
    return json.dumps(KEYBOARD_SHORTCUTS)
