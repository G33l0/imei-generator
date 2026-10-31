# main.py
import kivy
kivy.require('2.1.0')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window

from imei_generator import generate_imei_with_tac

Window.clearcolor = (0.1, 0.1, 0.1, 1)

class IMEIGeneratorApp(App):
    def build(self):
        self.title = 'eSIM iPhone IMEI Generator'
        
        main_layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        title_label = Label(
            text='[b]eSIM iPhone IMEI Generator[/b]',
            markup=True,
            font_size='24sp',
            size_hint_y=None,
            height=50
        )
        main_layout.add_widget(title_label)

        tac_layout = BoxLayout(size_hint_y=None, height=60, spacing=10)
        tac_label = Label(text='Select model:', size_hint_x=0.4)
        self.tac_spinner = Spinner(
            text='iPhone XR',
            values=('iPhone XR', 'iPhone 11', 'iPhone 12', 'iPhone 13', 'iPhone 14', 'iPhone 15', 'Custom TAC'),
            size_hint_x=0.6
        )
        tac_layout.add_widget(tac_label)
        tac_layout.add_widget(self.tac_spinner)
        main_layout.add_widget(tac_layout)

        self.custom_tac_input = TextInput(
            hint_text='Enter 8-digit TAC prefix',
            multiline=False,
            size_hint_y=None,
            height=50,
            opacity=0
        )
        main_layout.add_widget(self.custom_tac_input)
        self.tac_spinner.bind(text=self.on_tac_select)

        generate_btn = Button(
            text='Generate IMEI',
            size_hint_y=None,
            height=60,
            background_color=(0.2, 0.7, 0.3, 1)
        )
        generate_btn.bind(on_press=self.generate_imei)
        main_layout.add_widget(generate_btn)

        result_scroll = ScrollView(size_hint=(1, 0.6))
        self.result_label = Label(
            text='Press the button to generate an IMEI...',
            font_size='18sp',
            size_hint_y=None,
            halign='center',
            valign='middle'
        )
        self.result_label.bind(width=lambda instance, value: setattr(instance, 'text_size', (value, None)))
        result_scroll.add_widget(self.result_label)
        main_layout.add_widget(result_scroll)

        return main_layout

    def on_tac_select(self, spinner, text):
        if text == 'Custom TAC':
            self.custom_tac_input.opacity = 1
        else:
            self.custom_tac_input.opacity = 0

    def generate_imei(self, instance):
        selected_model = self.tac_spinner.text
        
        tac_db = {
            'iPhone XR': '35084958',
            'iPhone 11': '35307510',
            'iPhone 12': '35407115',
            'iPhone 13': '35695917',
            'iPhone 14': '35695917',
            'iPhone 15': '35332510',
        }
        
        try:
            if selected_model == 'Custom TAC':
                tac = self.custom_tac_input.text.strip()
                if len(tac) != 8 or not tac.isdigit():
                    self.result_label.text = '[color=ff0000]Error: Enter a valid 8-digit TAC[/color]'
                    self.result_label.markup = True
                    return
            else:
                tac = tac_db.get(selected_model)
                if not tac:
                    self.result_label.text = '[color=ff0000]Error: TAC not found for this model[/color]'
                    self.result_label.markup = True
                    return
            
            imei = generate_imei_with_tac(tac)
            self.result_label.markup = True
            self.result_label.text = f'[color=00ff00]Generated IMEI ({selected_model}):[/color]\n\n[b]{imei}[/b]'
            
        except Exception as e:
            self.result_label.text = f'[color=ff0000]Generation failed: {str(e)}[/color]'
            self.result_label.markup = True

if __name__ == '__main__':
    IMEIGeneratorApp().run()