"""
Hardware control modules for VCI-100 AI DJ Mixer.

This package handles physical hardware interactions:
- midi_controller: Vestax VCI-100 MIDI controller integration
"""

from .midi_controller import MIDIController

__all__ = [
    'MIDIController',
]
