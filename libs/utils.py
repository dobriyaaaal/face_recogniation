import os
import shutil
import json

def get_people_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'people'))

def load_people():
    people_dir = get_people_dir()
    if not os.path.exists(people_dir):
        os.makedirs(people_dir)
    return [name for name in os.listdir(people_dir) if os.path.isdir(os.path.join(people_dir, name))]

def delete_person(name):
    people_dir = get_people_dir()
    person_path = os.path.join(people_dir, name)
    if os.path.exists(person_path):
        shutil.rmtree(person_path)
        return True
    return False