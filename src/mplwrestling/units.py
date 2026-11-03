"""Shared pint unit registry.

Every module imports ``ureg`` from here. pint refuses to combine quantities
made by two different registries, so the library must only ever create one.
"""
import pint

ureg = pint.UnitRegistry()

#: Special unit name: lengths divided by the mat's competition radius, so the
#: edge of the wrestling area is 1.0 on every mat style.
MAT_UNITS = "mat_units"


def as_unit(units):
    """Turn a unit name such as ``"feet"``, ``"ft"`` or ``"meters"`` into a pint Unit.

    Plain strings are what users will pass, but ``Quantity.to`` behaves most
    predictably with a Unit object, so we parse once here.
    """
    if isinstance(units, pint.Unit):
        return units
    try:
        unit = ureg.Unit(units)
    except (pint.UndefinedUnitError, AttributeError, ValueError) as err:
        raise ValueError(f"'{units}' is not a unit pint understands. "
                         f"Try 'feet', 'meters', 'inches' or '{MAT_UNITS}'.") from err
    if not unit.is_compatible_with(ureg.meter):
        raise ValueError(f"'{units}' is not a length unit.")
    return unit
