"""App navigation commands, separate from desktop intent contracts."""
OMARCHY_MENU_FORMS = (
    'bring up the omarchy main menu', 'open omarchy menu',
    'open the omarchy menu', 'open the omarchy main menu',
    'show omarchy menu', 'show the omarchy main menu',
)
OMARCHY_MENU_SUGGESTION = dict(command='ui:omarchy-menu',
    text='open the omarchy main menu', forms=list(OMARCHY_MENU_FORMS))
