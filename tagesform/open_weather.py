
from datetime import datetime
import requests

from utils.config import config


class OpenWeatherResponse:
    def __init__(self, current_json, forecast_json=None):
        self.datetime = datetime.fromtimestamp(current_json['dt'])
        self.city = current_json["name"] + ", " + current_json["sys"]["country"] if "name" in current_json else None
        self.temperature = int(round(float(current_json['main']['temp']), 0))
        self.feels_like = int(round(float(current_json['main']['feels_like']), 0))
        self.humidity = str(current_json["main"]["humidity"]) + "%"
        self.pressure = str(current_json["main"]["pressure"]) + " hPa"
        self.wind = str(current_json["wind"]["speed"]) + " miles per hour" if "wind" in current_json else None
        if "rain" in current_json:
            rain_obj = current_json["rain"]
            hours = list(rain_obj.keys())[-1]
            inches = rain_obj[hours]
            self.rain = str(inches) + " inches in " + hours
        else:
            self.rain = None
        self.clouds = str(current_json["clouds"]["all"]) + "%" if "clouds" in current_json else None
        self.description = current_json["weather"][0]["main"] + ", " + current_json["weather"][0]["description"]
        self.sunrise = datetime.fromtimestamp(current_json["sys"]["sunrise"]).strftime("%H:%M") if "sunrise" in current_json["sys"] else None
        self.sunset = datetime.fromtimestamp(current_json["sys"]["sunset"]).strftime("%H:%M") if "sunset" in current_json["sys"] else None
        self.hourly_forecast = {}
        if forecast_json is not None:
            for i in range(len(forecast_json["list"])):
                hourly_data = forecast_json["list"][i]
                hour = datetime.fromtimestamp(hourly_data['dt']).strftime("%Y-%m-%d %H:%M")
                self.hourly_forecast[hour] = OpenWeatherResponse(hourly_data)

    def rain_in_next_5_days(self):
        hours_with_rain = {}
        for hour, hourly_data in self.hourly_forecast.items():
            if hourly_data.rain is not None:
                date = hourly_data.datetime.strftime("%m/%d (%A)")
                if date not in hours_with_rain:
                    hours_with_rain[date] = []
                hours_with_rain[date].append(hourly_data.datetime.strftime("%H:%M"))
        return hours_with_rain

    def forecast_min_max_temps_by_day(self):
        data = {}
        for hour, hourly_data in self.hourly_forecast.items():
            date = hourly_data.datetime.strftime("%m/%d (%A)")
            if date in data:
                if hourly_data.temperature > data[date]["max_temp"]:
                    data[date]["max_temp"] = hourly_data.temperature
                elif hourly_data.temperature < data[date]["min_temp"]:
                    data[date]["min_temp"] = hourly_data.temperature
                if hourly_data.rain is not None:
                    data[date]["rain"] = True
            else:
                data[date] = {"max_temp": hourly_data.temperature, "min_temp": hourly_data.temperature, "rain": hourly_data.rain is not None}
        return data

    def __str__(self):
        out = f"""Current weather details for {self.datetime.strftime("%A %B %d at %H:%M")}
City: {self.city}
Temperature: {self.temperature}°F
Feels Like: {self.feels_like}°F"""
        if self.rain is not None:
            out += f"\nRain: {self.rain}"
        if self.wind is not None:
            out += f"\nWind Speed: {self.wind}"
        out += f"""
Humidity: {self.humidity}
Pressure: {self.pressure}
Description: {self.description}
Sunrise: {self.sunrise} hours
Sunset: {self.sunset} hours"""
        if self.hourly_forecast is not None:
            out += "\nForecast"
            hours_with_rain = self.rain_in_next_5_days()
            for date, date_data in self.forecast_min_max_temps_by_day().items():
                out += f"\n{date}: Max {date_data['max_temp']}°F Min {date_data['min_temp']}°F"
                if date_data['rain'] and date in hours_with_rain:
                    out += f"  Rainy hours: {', '.join(hours_with_rain[date])}"
        return out

class OpenWeatherAPI:
    WEATHER_ENDPOINT = "https://api.openweathermap.org/data/2.5/weather"
    HOURLY_FORECAST_ENDPOINT = "https://api.openweathermap.org/data/2.5/forecast"
    GEO_ENDPOINT = "https://api.openweathermap.org/geo/1.0/direct"
    api_key = config.open_weather_api_key
    
    def __init__(self):
        pass

    def get_coordinates(self, city=config.open_weather_city):
        url = f"{self.GEO_ENDPOINT}?q={city}&limit=3&appid={self.api_key}"
        response = requests.get(url)
        resp_json = response.json()[0]
        return float(resp_json["lat"]), float(resp_json["lon"])

    def get_weather_for_city(self, city):
        lat, lon = self.get_coordinates(city)

        current_weather_url = f"{self.WEATHER_ENDPOINT}?lat={lat}&lon={lon}&appid={self.api_key}&units=imperial"
        current_weather_response = requests.get(current_weather_url)

        hourly_forecast_url = f"{self.HOURLY_FORECAST_ENDPOINT}?lat={lat}&lon={lon}&appid={self.api_key}&units=imperial"
        hourly_forecast_response = requests.get(hourly_forecast_url)

        weather = OpenWeatherResponse(current_weather_response.json(), hourly_forecast_response.json())
        return weather



if __name__ == "__main__":
    api = OpenWeatherAPI()
    api.get_weather_for_city("Washington")
