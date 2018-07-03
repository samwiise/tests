import bitarray
from datetime import datetime,timedelta
from tinydb import TinyDB, Query
from flask import Flask
from flask import request, jsonify
from tinydb.storages import MemoryStorage


app = Flask(__name__)


db = TinyDB(storage=MemoryStorage)


# Returns the date of the next given weekday after
# the given date. For example, the date of next Monday.
onDay = lambda date, day: date + timedelta(days=(day-date.weekday()+7)%7)

# =============================== Utils =========================================
class TimeSlotsMap(object):

    """
    Store and manipulate Time Slots for particular datetime range in memory, in a bitarray data structure for easy comparision.
    """

    def  __init__(self, start_time, end_time, slot_unit_size_seconds=3600,  initial_string=None):


        self.slot_unit_size_seconds = slot_unit_size_seconds

        self.start_time = self.normalize_to_unit_size_boundary(start_time.replace(microsecond=0), ceil=True)
        self.end_time = self.normalize_to_unit_size_boundary(end_time.replace(microsecond=0))

        units_delta = int((self.end_time - self.start_time).total_seconds()/self.slot_unit_size_seconds)


        if initial_string:
            if len(initial_string) != units_delta:
                raise Exception("time range and initial string doesn't match")
            self._bits_map = bitarray.bitarray(initial_string)
        else:
            self._bits_map = bitarray.bitarray(units_delta)
            self._bits_map.setall(0)


    def normalize_to_unit_size_boundary(self, slot_datetime, ceil=False):
        epoch_seconds = (slot_datetime - datetime.utcfromtimestamp(0)).total_seconds()
        if ceil:
            return slot_datetime + timedelta(
                seconds=(self.slot_unit_size_seconds - ((epoch_seconds - 1) % self.slot_unit_size_seconds) - 1))
        else:
            return slot_datetime - timedelta(
                seconds=(epoch_seconds % self.slot_unit_size_seconds))



    def map_size_seconds(self):
        return (self.end_time - self.start_time).total_seconds()


    def overlay_slots_map(self, time_slots_map, start_time=None, end_time=None,  repeat=False):

        """
        Overlay another Time Slots map pattern to this one, repeat the pattern between particular datetime range

        :type time_slots_map: TimeSlotsMap
        :type start_time: datetime
        :type end_time: datetime
        :type repeat: bool
        """
        assert isinstance(time_slots_map, TimeSlotsMap)
        assert time_slots_map.slot_unit_size_seconds == self.slot_unit_size_seconds

        if not start_time or start_time < self.start_time:
            start_time = self.start_time
        else:
            start_time = start_time.replace(microsecond=0)

        if not end_time or end_time > self.end_time:
            end_time = self.end_time
        else:
            end_time = end_time.replace(microsecond=0)


        #out of this time slots map range or 0 range
        if end_time<=start_time:
            return



        boundary_size_seconds  = time_slots_map.map_size_seconds()
        epoch_seconds = (start_time - datetime.utcfromtimestamp(0)).total_seconds()
        skip_start_units =  int((epoch_seconds % boundary_size_seconds)/self.slot_unit_size_seconds)

        map_offset = int((start_time - self.start_time).total_seconds()/self.slot_unit_size_seconds)
        map_end_index =  int((end_time - self.start_time).total_seconds()/self.slot_unit_size_seconds)

        while True:
            skip_end_units = max((map_offset + (time_slots_map._bits_map.length() - skip_start_units)) - map_end_index, 0)
            end_index = time_slots_map._bits_map.length() - skip_end_units

            self._bits_map[map_offset:map_offset + (end_index - skip_start_units)] = time_slots_map._bits_map[skip_start_units:end_index]

            map_offset += (end_index - skip_start_units)

            if not repeat or map_offset>=map_end_index:
                break
            skip_start_units=0



    def get_marked_slots_times(self, format_string=None):
        """
        Get list of marked time slots.
        :param format_string:
        :return:
        """

        marked_slots_times = []
        for i in range(0,self._bits_map.length()):

            if self._bits_map[i]:
                slot_start_time = self.start_time +  timedelta(seconds=self.slot_unit_size_seconds * i)
                slot_end_time = slot_start_time  + timedelta(seconds=self.slot_unit_size_seconds)

                if format_string:
                    marked_slots_times.append((datetime.strftime(slot_start_time,format_string),
                                               datetime.strftime(slot_end_time, format_string)))
                else:
                    marked_slots_times.append((slot_start_time,slot_end_time))

        return marked_slots_times


    def mark_slots(self, start_slot, count=1):
        """
        Mark slots available.

        :param start_slot:
        :param count:
        :return:
        """
        assert 1 <= start_slot <= self._bits_map.length(), "%d start_slot is out of range" % start_slot
        self._bits_map[start_slot-1:start_slot-1+count] = 1


    def reset(self):
        self._bits_map.setall(0)


    def merge_map(self, time_slots_map, intersect=False):
        """
        Merge two Time Slots Map with equal dimensions with UNION or INTERSECTION option
        :param time_slots_map:
        :param intersect:
        :return:
        """
        assert self.slot_unit_size_seconds == time_slots_map.slot_unit_size_seconds \
            and self._bits_map.length() == time_slots_map._bits_map.length(), \
            "time slots maps are not identical in dimensions"

        if intersect:
            self._bits_map &= time_slots_map._bits_map
        else:
            self._bits_map |= time_slots_map._bits_map


    def __str__(self):
        return self._bits_map.to01()


class TimeHourSlotsInOneDay(TimeSlotsMap):

    def __init__(self, initial_value=None):

        slot_unit_size_seconds = 3600

        start_time = datetime.utcfromtimestamp(0)
        end_time = datetime.utcfromtimestamp(60 * 60 * 24)


        if initial_value and isinstance(initial_value,int):
            day_bits = (end_time-start_time).total_seconds()/slot_unit_size_seconds
            initial_string = ('{0:0%sb}' % day_bits).format(initial_value)
        elif initial_value and isinstance(initial_value, str):
            initial_string = initial_value
        else:
            initial_string = None


        super(TimeHourSlotsInOneDay, self).__init__(initial_string=initial_string, slot_unit_size_seconds=slot_unit_size_seconds,
            start_time=start_time, end_time=end_time)

    def mark_hour_slots(self, start_hour, count=1):
        assert 0 <= start_hour <= 23, "%d start_hours is out of range" % start_hour

        self.mark_slots(start_slot=start_hour+1, count=count)



def parse_datetime_str(datetime_str, default=None):
    if datetime_str:
        return datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S")
    return default



def get_time_slots_map_for_user(start_time, end_time, user):

    """
    Generate Time Slot map for a user for specified date range from schedule data from db for the user
    :param start_time:
    :param end_time:
    :param user:
    :return:
    """

    time_slots_map = TimeSlotsMap(start_time=start_time, end_time=end_time)

    user_query = Query()
    schedules = db.search(user_query.user == user)

    schedules.sort(key=lambda x:x['created_time'])

    for sc in schedules:
        day_sc_map = TimeHourSlotsInOneDay(initial_value=str(sc["available_hours_in_a_day"]))

        sc_start_time = parse_datetime_str(sc.get("start_time"))
        sc_end_time = parse_datetime_str(sc.get("end_time"))

        time_slots_map.overlay_slots_map(time_slots_map=day_sc_map,start_time=sc_start_time,
                                         end_time=sc_end_time, repeat=True)

    return time_slots_map

# =======================================================================


# ================================== Flask APIs =================================

@app.route("/schedules", methods=['GET', 'DELETE'])
@app.route("/schedules/<string:user>/<string:id>", methods=['DELETE'])
@app.route("/schedules/<string:user>", methods=['POST', 'GET', 'DELETE'])
def availability_schedule(user=None, id=None):

    if request.method == "POST":
        data = request.get_json(force=True)

        if not "schedules" in data:
            return "invalid format\n",400

        for schedule in data.get("schedules",[]):

            #start_time = datetime.strptime(schedule["start_time"],"%Y-%m-%dT%H:%M:%S") if "start_time" in schedule else None
            #end_time = datetime.strptime(schedule["end_time"], "%Y-%m-%dT%H:%M:%S") if "end_time" in schedule else None

            db.insert({"user":user, "start_time": schedule.get("start_time"), "end_time": schedule.get("end_time"),
                    "available_hours_in_a_day": schedule.get("available_hours_in_a_day"),
                    "created_time": datetime.strftime(datetime.utcnow(),"%Y-%m-%dT%H:%M:%S")})

        return "",201
    elif request.method == "GET":
        if user:
            user_query = Query()
            schedules = db.search(user_query.user == user)
        else:
            schedules = db.all()

        for sc in schedules:
            sc["id"] = sc.doc_id

        return jsonify({"schedules":schedules})
    elif request.method == "DELETE":
        if id:
            if db.contains(doc_ids=[int(id)]):
                db.remove(doc_ids=[int(id)])
            else:
                return "",204
        else:
            if user:
                user_query = Query()
                schedules = db.search(user_query.user == user)
            else:
                schedules = db.all()

            doc_ids = [sc.doc_id for sc in schedules]
            if doc_ids:
                db.remove(doc_ids=doc_ids)

        return "",200


@app.route("/available_interview_slots/<string:candidate>", methods=["POST"])
def find_interview_slots(candidate):

    data = request.get_json(force=True)

    if not "interviewers" in data:
        return "invalid format\n", 400

    range_start_time = parse_datetime_str(data.get("range_start_time"))
    range_end_time = parse_datetime_str(data.get("range_end_time"))

    if not range_start_time:
        range_start_time = onDay(datetime.utcnow().replace(hour=0,minute=0,second=0),0)
        range_end_time = range_start_time +  timedelta(days=7)
    elif not range_end_time:
        range_end_time = range_start_time + timedelta(days=7)
    elif range_end_time<=range_start_time:
        return "Invalid date range specified\n", 400



    time_slots_maps =  get_time_slots_map_for_user(start_time=range_start_time, end_time=range_end_time,user=candidate)

    for interviewer in data["interviewers"]:
        intv_slot_map = get_time_slots_map_for_user(start_time=range_start_time, end_time=range_end_time,user=interviewer)
        time_slots_maps.merge_map(time_slots_map=intv_slot_map, intersect=True)


    availability_slots = time_slots_maps.get_marked_slots_times(format_string="%Y-%m-%dT%H:%M:%S")

    return jsonify({"available_slots":availability_slots})


# =============================================================================


def initialize_sample_data():

    day_hours = TimeHourSlotsInOneDay()

    day_hours.mark_hour_slots(start_hour=9, count=1)

    db.insert({"user":"Carl", "start_time": "2018-07-02T00:00:00", "end_time": "2018-07-07T00:00:00",
                    "available_hours_in_a_day": str(day_hours) ,
                    "created_time": "2018-06-06T00:00:00"})

    day_hours.reset()
    day_hours.mark_hour_slots(start_hour=10,count=2)

    db.insert({"user":"Carl", "start_time": "2018-07-04T00:00:00", "end_time": "2018-07-05T00:00:00",
                    "available_hours_in_a_day": str(day_hours) ,
                    "created_time": "2018-06-06T00:00:01"})

    day_hours.reset()
    day_hours.mark_hour_slots(start_hour=9, count=6)

    db.insert({"user": "Philipp", "start_time": "2018-07-02T00:00:00", "end_time": "2018-07-07T00:00:00",
               "available_hours_in_a_day": str(day_hours),
               "created_time": "2018-06-06T00:00:02"})

    day_hours.reset()
    day_hours.mark_hour_slots(start_hour=12, count=6)
    db.insert({"user": "Sarah", "start_time": "2018-07-02T00:00:00", "end_time": "2018-07-05T00:00:00",
               "available_hours_in_a_day": str(day_hours),
               "created_time": "2018-06-06T00:00:03"})

    day_hours.reset()
    day_hours.mark_hour_slots(start_hour=9, count=3)
    db.insert({"user": "Sarah", "start_time": "2018-07-03T00:00:00", "end_time": "2018-07-04T00:00:00",
               "available_hours_in_a_day": str(day_hours),
               "created_time": "2018-06-06T00:00:04"})

    db.insert({"user": "Sarah", "start_time": "2018-07-05T00:00:00", "end_time": "2018-07-06T00:00:00",
               "available_hours_in_a_day": str(day_hours),
               "created_time": "2018-06-06T00:00:05"})





if __name__ == "__main__":

    initialize_sample_data()

    app.run(debug=True,host="0.0.0.0")