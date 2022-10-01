# !/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import smtplib as smtplib
import time
import adafruit_dht
from azure.iot.device import IoTHubDeviceClient, Message
from twilio.rest import Client
import argparse
from board import *
from email.mime.text import MIMEText


# MAIL FUNCTIONS #
def send_mail(body):
    # this function connects to the mail server, and sends an e-mail
    try:
        conn = smtplib.SMTP_SSL('smtp.mail.yahoo.com', 465)
        conn.ehlo()
        conn.login(mail_user, mail_password)

        msg = MIMEText(body, ' plain')
        msg['Subject'] = body
        msg['From'] = mail_user

        conn.sendmail(mail_user,
                      mail_to,
                      msg.as_string())
        conn.quit()
    except Exception as e:
        print("failure to send an e-mail. Not sending e-mail because that would be e-mailception")
        print(e)


def create_email_body(ambienttemp_humidity, temperature_list):
    # given the ambient temperature, humidity and temperature sensors, this function dynamically creates an e-mail
    # message to send to the gmail account
    try:
        email_body = "current temperature between: "
        i = 1
        for temperature in temperature_list:
            if i < len(temperature_list):
                email_body = '{} {} and '.format(email_body, str(temperature))
            else:
                email_body = '{} {}.'.format(email_body, str(temperature))
            i = i + 1

        body = '{} And ambient temp is {} with a humidity of {}%.'\
            .format(email_body, str(ambienttemp_humidity[0]), str(ambienttemp_humidity[1]))
        return body
    except Exception as e:
        body_text = "raspberry pi was unable to create a needed e-mail body with errorcode " + str(e)
        print(body_text)
        send_mail(body_text)
        return ""


# AZURE IOT HUB FUNCTIONS #
def iothub_client_init():
    # Create an IoT Hub client, used for sending telemetry data
    iothub_client = IoTHubDeviceClient.create_from_connection_string(
        connection_string)

    return iothub_client


def iothub_client_send_telemetry(ambienttemp, humidity, temperature_list):
    # This function creates a json message from the collected telemetry data
    # and sends it to the Azure IOT hub
    try:
        msg_txt_formatted = "{" + '"ambienttemp": {}, "humidity": {}'.format(ambienttemp, humidity)
        i = 1
        for temperature in temperature_list:
            if i < len(temperature_list):
                msg_txt_formatted = '{}, "temperature{}": {}'.format(msg_txt_formatted, i, temperature)
            else:
                msg_txt_formatted = '{}, "temperature{}": {}'.format(msg_txt_formatted, i, temperature) + "}"
            i = i + 1
        print("Sending message: {}".format(msg_txt_formatted))
        message = Message(msg_txt_formatted)

        message.content_encoding = "utf-8"
        message.content_type = "application/json"

        client.send_message(message)
        print("Message successfully sent to IOT hub")
    except Exception as e:
        body_text = "raspberry pi was unable to send telemetry with errorcode " + str(e)
        print(body_text)
        send_mail(body_text)


# SENSOR READING FUCNTIONS #
def list_sensor_directories():
    # This function lists all directories containing temperature sensors
    # The rest of this code could potentially expect exactly 3 temperature sensors to exist
    try:
        root_directory = os.listdir('/sys/bus/w1/devices')  # Directory where all w1 sensors are
        sensor_directory_list = [k for k in root_directory if '28' in k]  # All sensors start with 28
        return sensor_directory_list
    except Exception as e:
        body_text = "raspberry pi was unable list directories with errorcode " + str(e)
        print(body_text)
        send_mail(body_text)


def read_temperature_sensor(directory):
    # This function reads temperature data from a specific sensor
    # The needed sensor readings are collected
    # The temperature data is Farenheit, hence it needs to be converted to Celcius
    try:
        tfile = open(directory)
        sensor_result = tfile.read()
        tfile.close()
        second_line = sensor_result.split("\n")[1]
        temperature = float(second_line.split(" ")[9][2:])
        celsius = temperature / 1000
        return celsius
    except Exception as e:
        body_text = "The temperature sensors cannot be read, returning 0 value with errorcode " + str(e)
        print(body_text)
        send_mail(body_text)
        return 0


def read_all_temperature_sensors(sensor_directory_list):
    # This function reads temperature data from all sensors, using the readSensor function
    # The number of sensors can vary
    # Obtained observations are sorted
    try:
        list_directories = []
        for directory in sensor_directory_list:
            location_sensor = '/sys/bus/w1/devices/' + directory + '/w1_slave'
            list_directories.append(read_temperature_sensor(location_sensor))
        return sorted(list_directories)
    except Exception as e:
        body_text = "The list of temperatures cannot be created, returning empty list with errorcode " + str(e)
        print(body_text)
        send_mail(body_text)
        return []


def read_adafruit_sensor():
    # This function reads temperature/humidity data from the humidity sensor
    try:
        # GPIO17
        sensor_pin = D17

        dht22 = adafruit_dht.DHT22(sensor_pin, use_pulseio=False)

        temperature = dht22.temperature
        humidity = dht22.humidity
        return round(temperature, 2), round(humidity, 2)
    except Exception as e:
        body_text = "The adafruit sensor cannot be read, returning a tuple containing 0's with errorcode " + str(e)
        print(body_text)
        send_mail(body_text)
        return 0, 0


# CHECK & CALL FUNCTIONS
def call_lisa_using_alert(reason, ambient_temp, humidity, temperature_list):
    # This functions calls Lisa usihng a Twillio phone number
    twillio_client = Client(account_sid, auth_token)
    body = ", and temperatures are "
    i = 1
    for temperature in temperature_list:
        if i < len(temperature_list):
            body = "{} {} and ".format(body, str(temperature))
        else:
            body = "{} {}.".format(body, str(temperature))
        i = i + 1

    twillio_client.calls.create(twiml='<Response><Say>Hi Lisa,' +
                                      'There is something wrong with the terrarium. ' +
                                      'The reason is ' + reason + '.' +
                                      'Ambient temperature is ' + str(ambient_temp) +
                                      ', and humidity is ' + str(humidity) + str(body) +
                                      '. Go to Fluffy immediately</Say></Response>',
                                to=phonenumber_to,
                                from_=phonenumber_from
                                )
    print("called Lisa")


def check_all_sensors_and_alert(ambient_temp, humidity, temperature_list):
    try:
        # check ambienttemp
        if ambient_temp == 0:
            print('the humidity temperature sensor needs to be reset: {}'.format(str(ambient_temp)))
        elif ambient_temp > 40:
            print('ambient temperature is too high: {}'.format(str(ambient_temp)))
            reason = ' that the ambient temperature is too high with a value of {}.'.format(str(ambient_temp))
            call_lisa_using_alert(reason, ambient_temp, humidity, temperature_list)
        elif ambient_temp < 20:
            print('ambient temperature is too low: {}'.format(str(ambient_temp)))
            reason = ' that the ambient temperature is too low with a value of ' + str(ambient_temp) + '.'
            call_lisa_using_alert(reason, ambient_temp, humidity, temperature_list)
        else:
            print('ambient temperature is sufficient: ' + str(ambient_temp))

        # check the lower of the 2 sensors
        if temperature_list[0] > 45:
            print('temperature of cool side is too high')
            reason = ' that the temperaturesensor on  the cool side is too high, with a value of {}.'.format(str(temperature_list[0]))
            call_lisa_using_alert(reason, ambient_temp, humidity, temperature_list)
        else:
            print('temperature of 2 lower sensors are sufficient')

    except Exception as e:
        body_text = "raspberry pi was unable to do one of the checks with errorcode " + e
        print(body_text)
        send_mail(body_text)


# HELPER FUNCTIONS #
def telemetry_check_mail(send: int):
    # This function will (1) send telemetry (2) do checks (3) send a mail
    # list sensor directories
    sensor_directories = list_sensor_directories()
    # read in ambientHumidity sensor and temperature sensors
    ambient_temp_humidity = read_adafruit_sensor()
    temperature_list = read_all_temperature_sensors(sensor_directories)

    # send telemetry data
    iothub_client_send_telemetry(ambient_temp_humidity[0], ambient_temp_humidity[1], temperature_list)

    # check for needed alerts
    print("checking sensors")
    check_all_sensors_and_alert(ambient_temp_humidity[0], ambient_temp_humidity[1], temperature_list)

    if send == 1:
        # create the body of the e-mail and send
        subject = create_email_body(ambient_temp_humidity, temperature_list)
        print(subject)
        print("sending mail")
        send_mail(subject)


def loop():
    # The loop function has a 30 min time span
    # In the first 15 min, it will (1) send telemetry (2) do checks (3) send a mail
    # In the second 15 min, it will (1) send telemetry (2) do checks
    try:
        telemetry_check_mail(1)

        # sleep 15 mins
        time.sleep(900)

        telemetry_check_mail(0)

        # sleep 15 mins
        time.sleep(900)
    except Exception as e:
        body_text = "something is wrong with the pi, and other functions did not catch the error, with errorcode " + str(e)
        print(body_text)
        send_mail(body_text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mail_user', type=str, help='row to query')
    parser.add_argument("--mail_password", type=str, help ='help')
    parser.add_argument("--account_sid", type=str, help='help')
    parser.add_argument("--auth_token", type=str, help='help')
    parser.add_argument("--connection_string", type=str, help='help')
    parser.add_argument("--phonenumber_from", type=str, help='help')
    parser.add_argument("--phonenumber_to", type=str, help='help')
    namespace = parser.parse_args()

    mail_user = namespace.mail_user
    mail_to = "<e-mail>"
    mail_password = namespace.mail_password
    account_sid = namespace.account_sid
    auth_token = namespace.auth_token
    connection_string = namespace.connection_string
    phonenumber_from = namespace.phonenumber_from
    phonenumber_to = namespace.phonenumber_to
    try:
        client = iothub_client_init()
        true = True
        while true:
            loop()
    except Exception as f:
        true = True
        while true:
            body1 = "something is wrong with the pi, and other functions did not catch the error"
            print(body1)
            send_mail(body1, f)
            time.sleep(900)

    except KeyboardInterrupt:
        quit()