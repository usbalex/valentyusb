#!/usr/bin/env python3

import CrcMoose3 as crc

import unittest
from unittest import TestCase
from usbcore import *

class TestRxClockDataRecovery(TestCase):
    def test_basic_recovery(self):
        """
        This test covers basic clock and data recovery.
        """

        def get_output():
            """
            Record data output when line_state_valid is asserted.
            """
            valid = yield dut.line_state_valid
            if valid == 1:
                dj = yield dut.line_state_dj
                dk = yield dut.line_state_dk
                se0 = yield dut.line_state_se0
                se1 = yield dut.line_state_se1

                out = "%d%d%d%d" % (dj, dk, se0, se1)

                return {
                    "1000" : "j",
                    "0100" : "k",
                    "0010" : "0",
                    "0001" : "1",
                }[out]

            else:
                return ""

        def stim(glitch=-1):
            out_seq = ""
            clock = 0
            for bit in seq + "0":
                for i in range(4):
                    if clock != glitch:
                        yield usbp_raw.eq({'j':1,'k':0,'0':0,'1':1}[bit])
                    yield usbn_raw.eq({'j':0,'k':1,'0':0,'1':1}[bit])
                    yield
                    clock += 1
                    out_seq += yield from get_output()
            self.assertEqual(out_seq, "0" + seq)

        test_sequences = [
            "j",
            "k",
            "0",
            "1",
            "jk01",
            "jjjkj0j1kjkkk0k10j0k00011j1k1011"
        ]

        for seq in test_sequences:
            with self.subTest(seq=seq):
                usbp_raw = Signal()
                usbn_raw = Signal()

                dut = RxClockDataRecovery(usbp_raw, usbn_raw)

                run_simulation(dut, stim(), vcd_name="vcd/test_basic_recovery_%s.vcd" % seq)


        long_test_sequences = [
            "jjjkj0j1kjkkk0k10j0k00011j1k1011",
            "kkkkk0k0kjjjk0kkkkjjjkjkjkjjj0kj"
        ]

        for seq in long_test_sequences:
            for glitch in range(0, 32, 8):
                with self.subTest(seq=seq, glitch=glitch):
                    usbp_raw = Signal()
                    usbn_raw = Signal()

                    dut = RxClockDataRecovery(usbp_raw, usbn_raw)

                    run_simulation(dut, stim(glitch), vcd_name="vcd/test_basic_recovery_%s_%d.vcd" % (seq, glitch))



class TestRxNRZIDecoder(TestCase):
    def test_nrzi(self):

        def send(valid, value):
            valid += "_"
            value += "_"
            output = ""
            for i in range(len(valid)):
                yield i_valid.eq(valid[i] == '-')
                yield i_dj.eq(value[i] == 'j')
                yield i_dk.eq(value[i] == 'k')
                yield i_se0.eq(value[i] == '_')
                yield

                o_valid = yield dut.o_valid
                if o_valid:
                    data = yield dut.o_data
                    se0 = yield dut.o_se0

                    out = "%d%d" % (data, se0)

                    output += {
                        "10" : "1",
                        "00" : "0",
                        "01" : "_",
                        "11" : "_"
                    }[out]
            return output

        test_vectors = [
            dict(
                # USB2 Spec, 7.1.8
                valid  = "-----------------",
                value  = "jkkkjjkkjkjjkjjjk",
                output = "10110101000100110"
            ),

            dict(
                # USB2 Spec, 7.1.9.1
                valid  = "--------------------",
                value  = "jkjkjkjkkkkkkkjjjjkk",
                output = "10000000111111011101"
            ),

            dict(
                # USB2 Spec, 7.1.9.1 (added pipeline stalls)
                valid  = "------___--------------",
                value  = "jkjkjkkkkjkkkkkkkjjjjkk",
                output = "10000000111111011101"
            ),

            dict(
                # USB2 Spec, 7.1.9.1 (added pipeline stalls 2)
                valid  = "-------___-------------",
                value  = "jkjkjkjjjjkkkkkkkjjjjkk",
                output = "10000000111111011101"
            ),

            dict(
                # USB2 Spec, 7.1.9.1 (added pipeline stalls 3)
                valid  = "-------___-------------",
                value  = "jkjkjkjkkkkkkkkkkjjjjkk",
                output = "10000000111111011101"
            ),

            dict(
                # USB2 Spec, 7.1.9.1 (added pipeline stalls, se0 glitch)
                valid  = "-------___-------------",
                value  = "jkjkjkj__kkkkkkkkjjjjkk",
                output = "10000000111111011101"
            ),

            dict(
                # Captured setup packet
                valid  = "------------------------------------",
                value  = "jkjkjkjkkkjjjkkjkjkjkjkjkjkjkkjkj__j",
                output = "100000001101101000000000000001000__1"
            ),

            dict(
                # Captured setup packet (pipeline stalls)
                valid  = "-___----___--------___-___-___-___----------------___-___---",
                value  = "jjjjkjkjjkkkjkkkjjjjjkkkkkkkkkjjjjkjkjkjkjkjkjkkjkkkkj_____j",
                output = "100000001101101000000000000001000__1"
            )

        ]

        def stim(valid, value, output):
            actual_output = yield from send(valid, value)
            self.assertEqual(actual_output, output)

        i = 0
        for vector in test_vectors:
            with self.subTest(i=i, vector=vector):
                i_valid = Signal()
                i_dj = Signal()
                i_dk = Signal()
                i_se0 = Signal()

                dut = RxNRZIDecoder(i_valid, i_dj, i_dk, i_se0)

                run_simulation(dut, stim(**vector), vcd_name="vcd/test_nrzi_%d.vcd" % i)
                i += 1




class TestRxBitstuffRemover(TestCase):
    def test_bitstuff(self):

        def send(valid, value):
            valid += "_"
            value += "_"
            output = ""
            for i in range(len(valid)):
                yield i_valid.eq(valid[i] == '-')
                yield i_data.eq(value[i] == '1')
                yield i_se0.eq(value[i] == '_')
                yield

                o_valid = yield dut.o_valid
                bitstuff_error = yield dut.o_bitstuff_error
                if o_valid or bitstuff_error:
                    data = yield dut.o_data
                    se0 = yield dut.o_se0

                    out = "%d%d%d" % (data, se0, bitstuff_error)

                    output += {
                        "100" : "1",
                        "101" : "e",
                        "000" : "0",
                        "010" : "_",
                        "110" : "_"
                    }[out]
            return output

        test_vectors = [
            dict(
                # Basic bitstuff scenario
                valid  = "-------",
                value  = "1111110",
                output = "111111"
            ),

            dict(
                # Basic bitstuff scenario (valid gap)
                valid  = "---___----",
                value  = "111___1110",
                output = "111111"
            ),

            dict(
                # Basic bitstuff scenario (valid gap)
                valid  = "---___----",
                value  = "1111111110",
                output = "111111"
            ),

            dict(
                # Basic bitstuff scenario (valid gap)
                valid  = "---___----",
                value  = "1110001110",
                output = "111111"
            ),

            dict(
                # Basic bitstuff scenario (valid gap)
                valid  = "---___-____---",
                value  = "11100010000110",
                output = "111111"
            ),


            dict(
                # Basic bitstuff error
                valid  = "-------",
                value  = "1111111",
                output = "111111e"
            ),

            dict(
                # Multiple bitstuff scenario
                valid  = "---------------------",
                value  = "111111011111101111110",
                output = "111111111111111111"
            ),

            dict(
                # Mixed bitstuff error
                valid  = "---------------------------------",
                value  = "111111111111101111110111111111111",
                output = "111111e111111111111111111e11111"
            ),

            dict(
                # Idle, Packet, Idle
                valid  = "-------------------------------",
                value  = "111110000000111111011101__11111",
                output = "11111000000011111111101__11111"
            ),

            dict(
                # Idle, Packet, Idle, Packet, Idle
                valid  = "--------------------------------------------------------------",
                value  = "111110000000111111011101__11111111110000000111111011101__11111",
                output = "11111000000011111111101__111111e111000000011111111101__11111"
            ),

            dict(
                # Captured setup packet (no bitstuff)
                valid  = "------------------------------------",
                value  = "100000001101101000000000000001000__1",
                output = "100000001101101000000000000001000__1"
            )
        ]

        def stim(valid, value, output):
            actual_output = yield from send(valid, value)
            self.assertEqual(actual_output, output)

        i = 0
        for vector in test_vectors:
            with self.subTest(i=i, vector=vector):
                i_valid = Signal()
                i_data = Signal()
                i_se0 = Signal()

                dut = RxBitstuffRemover(i_valid, i_data, i_se0)

                run_simulation(dut, stim(**vector), vcd_name="vcd/test_bitstuff_%d.vcd" % i)
                i += 1




class TestRxPacketDetect(TestCase):
    def test_packet_detect(self):

        test_vectors = [
            dict(
                # SE0, Idle
                valid    = "------------------------------",
                value    = "______________1111111111111111",
                output_1 = "                               ",
                output_2 = "_______________________________"
            ),

            dict(
                # Idle, Packet, Idle
                valid    = "------------------------------",
                value    = "11111000000011111111101__11111",
                output_1 = "             S          E      ",
                output_2 = "_____________-----------_______"
            ),

            dict(
                # Idle, Packet, Idle (pipeline stall)
                valid    = "-------------___-----------------",
                value    = "11111000000011111111111101__11111",
                output_1 = "             S             E      ",
                output_2 = "_____________--------------_______"
            ),

            dict(
                # Idle, Packet, Idle (pipeline stalls)
                valid    = "-----___---___-----___-----------------",
                value    = "11111111000___000011111111111101__11111",
                output_1 = "                   S             E      ",
                output_2 = "___________________--------------_______"
            ),

            dict(
                # Idle, Packet, Idle, Packet, Idle
                valid    = "------------------------------------------------------------",
                value    = "11111000000011111111101__1111111111000000011111111101__11111",
                output_1 = "             S          E                  S          E      ",
                output_2 = "_____________-----------___________________-----------_______"
            ),

            dict(
                # Idle, Short Sync Packet, Idle
                valid    = "----------------------------",
                value    = "111110000011111111101__11111",
                output_1 = "           S          E      ",
                output_2 = "___________-----------_______"
            ),

            dict(
                # Idle Glitch
                valid    = "------------------------------",
                value    = "11111111110011111111_1111__111",
                output_1 = "                               ",
                output_2 = "_______________________________"
            ),
        ]

        def send(valid, value):
            valid += "_"
            value += "_"
            output_1 = ""
            output_2 = ""
            for i in range(len(valid)):
                yield i_valid.eq(valid[i] == '-')
                yield i_data.eq(value[i] == '1')
                yield i_se0.eq(value[i] == '_')
                yield

                pkt_start = yield dut.o_pkt_start
                pkt_end = yield dut.o_pkt_end

                out = "%d%d" % (pkt_start, pkt_end)

                output_1 += {
                    "10" : "S",
                    "01" : "E",
                    "00" : " ",
                }[out]

                pkt_active = yield dut.o_pkt_active

                out = "%d" % (pkt_active)

                output_2 += {
                    "1" : "-",
                    "0" : "_",
                }[out]

            return output_1, output_2

        def stim(valid, value, output_1, output_2):
            actual_output_1, actual_output_2 = yield from send(valid, value)
            self.assertEqual(actual_output_1, output_1)
            self.assertEqual(actual_output_2, output_2)

        i = 0
        for vector in test_vectors:
            with self.subTest(i=i, vector=vector):
                i_valid = Signal()
                i_data = Signal()
                i_se0 = Signal()

                dut = RxPacketDetect(i_valid, i_data, i_se0)

                run_simulation(dut, stim(**vector), vcd_name="vcd/test_packet_det_%d.vcd" % i)
                i += 1





class TestRxShifter(TestCase):
    def test_shifter(self):
        test_vectors = [
            dict(
                # basic shift in
                width    = 8,
                reset    = "-______________",
                valid    = "_--------------",
                value    = "001110100101010",
                full     = "_________------",
                output   = [0x2E]
            ),

            dict(
                # basic shift in (short pipeline stall)
                width    = 8,
                reset    = "-_______________",
                valid    = "_----_----------",
                value    = "0011100100101010",
                full     = "__________------",
                output   = [0x2E]
            ),

            dict(
                # basic shift in (long pipeline stall)
                width    = 8,
                reset    = "-_________________",
                valid    = "_----___----------",
                value    = "001110000100101010",
                full     = "____________------",
                output   = [0x2E]
            ),

            dict(
                # basic shift in (multiple long pipeline stall)
                width    = 8,
                reset    = "-__________________________",
                valid    = "_-___---___-___--___-------",
                value    = "000001110000111101110101010",
                full     = "_____________________------",
                output   = [0x2E]
            ),

            dict(
                # multiple resets
                width    = 8,
                reset    = "-______________-______________",
                valid    = "_--------------_--------------",
                value    = "010111000001101001110100101010",
                full     = "_________-------________------",
                output   = [0b00011101, 0x2E]
            ),

            dict(
                # multiple resets (tight timing)
                width    = 8,
                reset    = "-________-______________",
                valid    = "_-----------------------",
                value    = "000101001111000010011101",
                full     = "_________-________------",
                output   = [0b10010100, 0b01000011]
            ),
        ]

        def send(reset, valid, value):
            full = ""
            output = []
            for i in range(len(valid)):
                yield i_reset.eq(reset[i] == '-')
                yield i_valid.eq(valid[i] == '-')
                yield i_data.eq(value[i] == '1')
                yield

                o_full = yield dut.o_full
                put = yield dut.o_put

                if put:
                    last_output = yield dut.o_output
                    output.append(last_output)

                out = "%d" % (o_full)

                full += {
                    "1" : "-",
                    "0" : "_",
                }[out]

            return full, output

        def stim(width, reset, valid, value, full, output):
            actual_full, actual_output = yield from send(reset, valid, value)
            self.assertEqual(actual_full, full)
            self.assertEqual(actual_output, output)

        i = 0
        for vector in test_vectors:
            with self.subTest(i=i, vector=vector):
                i_valid = Signal()
                i_data = Signal()
                i_reset = Signal()

                dut = RxShifter(vector["width"], i_valid, i_data, i_reset)

                run_simulation(dut, stim(**vector), vcd_name="vcd/test_shifter_%d.vcd" % i)
                i += 1





class TestRxCrcChecker(TestCase):
    def test_shifter(self):
        def send(reset, valid, value):
            crc_good = ""
            for i in range(len(valid)):
                yield i_reset.eq(reset[i] == '-')
                yield i_valid.eq(valid[i] == '-')
                yield i_data.eq(value[i] == '1')
                yield

                o_crc_good = yield dut.o_crc_good

                out = "%d" % (o_crc_good)

                crc_good += {
                    "1" : "-",
                    "0" : "_",
                }[out]

            return crc_good

        test_vectors = [
            dict(
                # USB2 token with good CRC5 (1)
                width       = 5,
                polynomial  = 0b00101,
                initial     = 0b11111,
                residual    = 0b01100,
                reset       = "-___________________",
                valid       = "_----------------___",
                value       = "00000000000001000000",
                crc_good    = "_______-__________--"
            ),

            dict(
                # USB2 token with good CRC5 and pipeline stalls (1)
                width       = 5,
                polynomial  = 0b00101,
                initial     = 0b11111,
                residual    = 0b01100,
                reset       = "-_______________________________",
                valid       = "_-___-___------------___-___-___",
                value       = "00000011100000000001011100000000",
                crc_good    = "_____________-________________--"
            ),

            dict(
            # USB2 token with bad CRC5 (1)
                width       = 5,
                polynomial  = 0b00101,
                initial     = 0b11111,
                residual    = 0b01100,
                reset       = "-___________________",
                valid       = "_----------------___",
                value       = "00010000000001000000",
                crc_good    = "______-________-____"
            ),

            dict(
                # USB2 token with good CRC5 (2)
                width       = 5,
                polynomial  = 0b00101,
                initial     = 0b11111,
                residual    = 0b01100,
                reset       = "-___________________",
                valid       = "_----------------___",
                value       = "00000011011011101000",
                crc_good    = "_______-__________--"
            ),

            dict(
                # USB2 token with bad CRC5 (2)
                width       = 5,
                polynomial  = 0b00101,
                initial     = 0b11111,
                residual    = 0b01100,
                reset       = "-___________________",
                valid       = "_----------------___",
                value       = "00010011011011101000",
                crc_good    = "______-_____________"
            ),

            dict(
                # Two USB2 token with good CRC5 (1,2)
                width       = 5,
                polynomial  = 0b00101,
                initial     = 0b11111,
                residual    = 0b01100,
                reset       = "-________________________-___________________",
                valid       = "_----------------_________----------------___",
                value       = "000000000000010000000000000000011011011101000",
                crc_good    = "_______-__________---------_____-__________--"
            ),

            dict(
                # USB2 data with good CRC16 (1)
                width       = 16,
                polynomial  = 0b1000000000000101,
                initial     = 0b1111111111111111,
                residual    = 0b1000000000001101,
                reset       = "-______________________________________________________________________________________________",
                valid       = "_--------_--------_--------_--------_--------_--------_--------_--------_----------------______",
                value       = "00000000100110000000000000001000000000000000000000000000000001000000000001011101100101001000010",
                crc_good    = "__________________________________________________________________________________________-----"
            ),

            dict(
                # USB2 data with bad CRC16 (1)
                width       = 16,
                polynomial  = 0b1000000000000101,
                initial     = 0b1111111111111111,
                residual    = 0b1000000000001101,
                reset       = "-______________________________________________________________________________________________",
                valid       = "_--------_--------_--------_--------_--------_--------_--------_--------_----------------______",
                value       = "00000000100110000000000000001000000000010000000000000000000001000000000001011101100101001000010",
                crc_good    = "_______________________________________________________________________________________________"
            ),
        ]

        def stim(width, polynomial, initial, residual, reset, valid, value, crc_good):
            actual_crc_good = yield from send(reset, valid, value)
            self.assertEqual(actual_crc_good, crc_good)

        i = 0
        for vector in test_vectors:
            with self.subTest(i=i, vector=vector):
                i_valid = Signal()
                i_data = Signal()
                i_reset = Signal()

                dut = RxCrcChecker(
                    vector["width"],
                    vector["polynomial"],
                    vector["initial"],
                    vector["residual"],
                    i_valid,
                    i_data,
                    i_reset)

                run_simulation(dut, stim(**vector), vcd_name="vcd/test_crc_%d.vcd" % i)
                i += 1






class TestRxPacketDecode(TestCase):
    def test_pkt_decode(self):
        def send(valid, value):
            pid = []
            token_payload = []
            data_payload = []
            data = []
            pkt_good = []
            for i in range(len(valid)):
                yield i_valid.eq(valid[i] == '-')
                yield i_data.eq(value[i] == '1' or value[i] == 'B')
                yield i_se0.eq(value[i] == '_')
                yield i_bitstuff_error.eq(value[i] == 'B')
                yield

                o_pkt_start = yield dut.o_pkt_start
                o_pkt_pid = yield dut.o_pkt_pid
                o_pkt_token_payload = yield dut.o_pkt_token_payload
                o_pkt_data = yield dut.o_pkt_data
                o_pkt_data_put = yield dut.o_pkt_data_put
                o_pkt_good = yield dut.o_pkt_good
                o_pkt_end = yield dut.o_pkt_end

                if o_pkt_data_put:
                    data += [o_pkt_data]

                if o_pkt_end:
                    pid += [o_pkt_pid]
                    token_payload += [o_pkt_token_payload]
                    data_payload.append(data)
                    data = []
                    pkt_good += [o_pkt_good]

            return pid, token_payload, data_payload, pkt_good

        test_vectors = [
            dict(
                # USB2 SOF token
                valid           = "---------------------------------------",
                value           = "1100000001101001011000011011000010__111",
                pid             = [0b0101],
                token_payload   = [865],
                data_payload    = [[]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 SOF token - pipeline stalls
                valid           = "----------_--------_-----------_----------",
                value           = "1100000001_10100101_10000110110_00010__111",
                pid             = [0b0101],
                token_payload   = [865],
                data_payload    = [[]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 SOF token - eop dribble 1
                valid           = "----------_--------_-----------_-----_-----",
                value           = "1100000001_10100101_10000110110_00010_1__111",
                pid             = [0b0101],
                token_payload   = [865],
                data_payload    = [[]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 SOF token - eop dribble 6
                valid           = "----------_--------_-----------_-----_-----------",
                value           = "1100000001_10100101_10000110110_00010_111111__111",
                pid             = [0b0101],
                token_payload   = [865],
                data_payload    = [[]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 SOF token - bad pid
                valid           = "----------_--------_-----------_----------",
                value           = "1100000001_10100100_10000110110_00010__111",
                pid             = [0b0101],
                token_payload   = [865],
                data_payload    = [[]],
                pkt_good        = [0]
            ),

            dict(
                # USB2 SOF token - bad crc5
                valid           = "----------_--------_-----------_----------",
                value           = "1100000001_10100101_10000110110_00011__111",
                pid             = [0b0101],
                token_payload   = [865],
                data_payload    = [[]],
                pkt_good        = [0]
            ),

            dict(
                # USB2 SOF token - bitstuff error
                valid           = "----------_-----_____-_____--_-----------_----------",
                value           = "1100000001_10100_____B_____01_10000110110_00010__111",
                pid             = [0b0101],
                token_payload   = [865],
                data_payload    = [[]],
                pkt_good        = [0]
            ),

            dict(
                # USB2 ACK handshake
                valid           = "----------_-------------",
                value           = "1100000001_01001011__111",
                pid             = [0b0010],
                token_payload   = [0],
                data_payload    = [[]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 ACK handshake - late bitstuff error
                valid           = "----------_-------------",
                value           = "1100000001_0100101B__111",
                pid             = [0b0010],
                token_payload   = [0],
                data_payload    = [[]],
                pkt_good        = [0]
            ),


            dict(
                # USB2 ACK handshake - pid error
                valid           = "----------_-------------",
                value           = "1100000001_01001111__111",
                pid             = [0b0010],
                token_payload   = [0],
                data_payload    = [[]],
                pkt_good        = [0]
            ),

            dict(
                # USB2 ACK handshake - EOP dribble 1
                valid           = "----------_--------_-----",
                value           = "1100000001_01001011_1__111",
                pid             = [0b0010],
                token_payload   = [0],
                data_payload    = [[]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 ACK handshake - EOP dribble 6
                valid           = "----------_--------_-----------",
                value           = "1100000001_01001011_111111__111",
                pid             = [0b0010],
                token_payload   = [1792], # token payload doesn't matter in this test, but dribble triggers it
                data_payload    = [[]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 data with good CRC16 (1)
                valid       = "----------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_------",
                value       = "1100000001_11000011_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_00101001___1111",
                pid             = [0b0011],
                token_payload   = [1664], # token payload is a "don't care" for this test
                data_payload    = [[0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0x94]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 data with good CRC16 - 1 eop dribble
                valid       = "----------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_-_-----",
                value       = "1100000001_11000011_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_00101001_1___1111",
                pid             = [0b0011],
                token_payload   = [1664], # token payload is a "don't care" for this test
                data_payload    = [[0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0x94]],
                pkt_good        = [1]
            ),

            dict(
                # USB2 data with good CRC16 - 6 eop dribble
                valid       = "----------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_------_------",
                value       = "1100000001_11000011_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_00101001_111111___1111",
                pid             = [0b0011],
                token_payload   = [1664], # token payload is a "don't care" for this test
                data_payload    = [[0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0x94]],
                pkt_good        = [1]
            ),

            # TODO: need a better way to handle eop dribble with bitstuff error :(
            #dict(
            #    # USB2 data with good CRC16 - 1 eop dribble with bitstuff error
            #    valid       = "----------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_-_-----",
            #    value       = "1100000001_11000011_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_00101001_B___1111",
            #    pid             = [0b0011],
            #    token_payload   = [1664], # token payload is a "don't care" for this test
            #    data_payload    = [[0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0x94]],
            #    pkt_good        = [1]
            #),

            #dict(
            #    # USB2 data with good CRC16 - 6 eop dribble with bitstuff error
            #    valid       = "----------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_------_------",
            #    value       = "1100000001_11000011_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_00101001_11111B___1111",
            #    pid             = [0b0011],
            #    token_payload   = [1664], # token payload is a "don't care" for this test
            #    data_payload    = [[0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0x94]],
            #    pkt_good        = [1]
            #),

            dict(
                # USB2 data with bad CRC16 (1)
                valid       = "----------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_------",
                value       = "1100000001_11000011_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_00101011___1111",
                pid             = [0b0011],
                token_payload   = [1664], # token payload is a "don't care" for this test
                data_payload    = [[0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0xD4]],
                pkt_good        = [0]
            ),

            dict(
                # USB2 data with late bitstuff error
                valid       = "----------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_------",
                value       = "1100000001_11000011_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_0010100B___1111",
                pid             = [0b0011],
                token_payload   = [1664], # token payload is a "don't care" for this test
                data_payload    = [[0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0x94]],
                pkt_good        = [0]
            ),

            dict(
                # USB2 data with bad pid
                valid       = "----------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_------",
                value       = "1100000001_11000001_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_00101001___1111",
                pid             = [0b0011],
                token_payload   = [1664], # token payload is a "don't care" for this test
                data_payload    = [[0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0x94]],
                pkt_good        = [0]
            ),

            dict(
                # USB2 SETUP and DATA
                valid           = "----------_--------_-----------_----------___---------------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_--------_------",
                value           = "1100000001_10110100_00000000000_01000__111___111111100000001_11000011_00000001_01100000_00000000_10000000_00000000_00000000_00000010_00000000_10111011_00101001___1111",
                pid             = [0b1101,  0b0011],
                token_payload   = [0,       1664],
                data_payload    = [[],      [0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00, 0xdd, 0x94]],
                pkt_good        = [1,       1]
            ),
        ]


        def stim(valid, value, pid, token_payload, data_payload, pkt_good):
            actual_pid, actual_token_payload, actual_data_payload, actual_pkt_good = yield from send(valid, value)
            self.assertEqual(actual_pid, pid)
            self.assertEqual(actual_token_payload, token_payload)
            self.assertEqual(actual_data_payload, data_payload)
            self.assertEqual(actual_pkt_good, pkt_good)

        i = 0
        for vector in test_vectors:
            with self.subTest(i=i, vector=vector):
                i_valid = Signal()
                i_data = Signal()
                i_se0 = Signal()
                i_bitstuff_error = Signal()

                dut = RxPacketDecode(
                    i_valid,
                    i_data,
                    i_se0,
                    i_bitstuff_error)

                run_simulation(dut, stim(**vector), vcd_name="vcd/test_decode_%d.vcd" % i)
            i += 1




class TestTxShifter(TestCase):
    def test_shifter(self):
        test_vectors = [
            dict(
                # basic shift out
                width   = 8,
                data    = [0b10011000],
                put     = "-______________",
                shift   = "_--------------",
                output  = " 00011001      "
            ),

            dict(
                # basic shift out - pipeline stall
                width   = 8,
                data    = [0b10011000],
                put     = "-_______________",
                shift   = "_-_-------------",
                output  = " 000011001      "
            ),

            dict(
                # basic shift out - pipeline stall
                width   = 8,
                data    = [0b10011000],
                put     = "-________________",
                shift   = "__-_-------------",
                output  = " 0000011001      "
            ),

            dict(
                # basic shift out - pipeline stall
                width   = 8,
                data    = [0b10011000],
                put     = "-________________________",
                shift   = "____-_------___-___------",
                output  = " 000000011001111         "
            ),

            dict(
                # basic shift out - pipeline stalls
                width   = 8,
                data    = [0b10011000],
                put     = "-______________________________________",
                shift   = "_-___-___-___-___-___-___-___-___------",
                output  = " 00000000011111111000000001111         "
            ),

            dict(
                # basic shift out multiple
                width   = 8,
                data    = [0b10011000, 0b11001011],
                put     = "-________-___________",
                shift   = "_--------_--------___",
                output  = " 00011001 11010011   "
            ),

            dict(
                # basic shift out multiple
                width   = 8,
                data    = [0b10011000, 0b11001011],
                put     = "-_________-___________",
                shift   = "_--------__--------___",
                output  = " 00011001  11010011   "
            ),
        ]

        def send(shift, put, data):
            output = ""
            for i in range(len(shift)):
                do_put = put[i] == '-'

                if do_put:
                    yield i_data.eq(data.pop(0))

                yield i_put.eq(do_put)
                yield i_shift.eq(shift[i] == '-')

                yield

                o_empty = yield dut.o_empty
                o_data = yield dut.o_data

                out = "%d%d" % (o_empty, o_data)

                output += {
                    "00" : "0",
                    "01" : "1",
                    "10" : " ",
                    "11" : " ",
                }[out]

            return output

        def stim(width, data, put, shift, output):
            actual_output = yield from send(shift, put, data)
            self.assertEqual(actual_output, output)

        i = 0
        for vector in test_vectors:
            with self.subTest(i=i, vector=vector):
                i_put = Signal()
                i_shift = Signal()
                i_data = Signal(vector["width"])

                dut = TxShifter(vector["width"], i_put, i_shift, i_data)

                run_simulation(dut, stim(**vector), vcd_name="vcd/test_tx_shifter_%d.vcd" % i)
                i += 1


def create_tester(dut_type, **def_args):
    def run(self, **test_args):
        name = self.id()

        self.inputs = dict()
        self.outputs = dict()
        self.params = set()
        self.dut_args = dict()

        # parse tester definition
        for key in def_args:
            if not key.startswith("i_") and not key.startswith("o_"):
                self.params.add(key)

        for key in def_args:
            if key.startswith("i_"):
                width = def_args[key][0]

                if isinstance(width, str):
                    width = test_args[width]

                self.inputs[key] = Signal(def_args[key][0])

            if key.startswith("o_"):
                self.outputs[key] = None

        # create dut
        for p in self.params:
            self.dut_args[p] = test_args[p]

        for i in self.inputs.keys():
            self.dut_args[i] = self.inputs[i]

        dut = dut_type(**self.dut_args)

        # gather outputs
        for o in self.outputs.keys():
            self.outputs[o] = getattr(dut, o)

        # calc num clocks
        clocks = 0
        for i in set(self.inputs.keys()) | set(self.outputs.keys()):
            if isinstance(test_args[i], str):
                clocks = max(clocks, len(test_args[i]))

        # decode stimulus
        def decode(c):
            try:
                return int(c, 16)
            except:
                pass

            if c == "-":
                return 1

            return 0

        # error message debug helper
        def to_waveform(sigs):
            output = ""

            for name in sigs.keys():
                output += "%20s: %s\n" % (name, sigs[name])

            return output



        actual_output = dict()

        # setup stimulus
        def stim():

            for signal_name in self.outputs.keys():
                actual_output[signal_name] = ""

            for i in range(clocks):
                for input_signal in self.inputs.keys():
                    yield self.inputs[input_signal].eq(decode(test_args[input_signal][i]))

                yield

                for output_signal in self.outputs.keys():
                    actual_value = yield self.outputs[output_signal]
                    actual_output[output_signal] += str(actual_value)


                    if isinstance(test_args[output_signal], tuple):
                        if test_args[output_signal][0][i] == '*':
                            expected_value = decode(test_args[output_signal][1].pop(0))

                    elif test_args[output_signal] is not None:
                        if test_args[output_signal][i] != ' ':
                            expected_value = decode(test_args[output_signal][i])
                            details = "\n"
                            if actual_value != expected_value:
                                details += "            Expected: %s\n" % (test_args[output_signal])
                                details += "                      " + (" " * i) + "^\n"
                                details += to_waveform(actual_output)
                            self.assertEqual(actual_value, expected_value, msg = ("%s:%s:%d" % (name, output_signal, i)) + details)


        # run simulation
        run_simulation(dut, stim(), vcd_name="vcd/%s.vcd" % name)

        return actual_output

    return run

def module_tester(dut_type, **def_args):
    def wrapper(class_type):
        class_type.do = create_tester(dut_type, **def_args)
        return class_type

    return wrapper


@module_tester(
    TxCrcGenerator,

    width       = None,
    polynomial  = None,
    initial     = None,

    i_reset     = (1,),
    i_data      = (1,),
    i_shift     = (1,),

    o_crc       = ("width",)
)
class TestTxCrcGenerator(TestCase):
    def test_token_crc5_zeroes(self):
        self.do(
            width       = 5,
            polynomial  = 0b00101,
            initial     = 0b11111,

            i_reset     = "-_______________",
            i_data      = "  00000000000   ",
            i_shift     = "__-----------___",
            o_crc       = "             222"
        )

    def test_token_crc5_zeroes_alt(self):
        self.do(
            width       = 5,
            polynomial  = 0b00101,
            initial     = 0b11111,

            i_reset     = "-______________",
            i_data      = " 00000000000   ",
            i_shift     = "_-----------___",
            o_crc       = "            222"
        )

    def test_token_crc5_nonzero(self):
        self.do(
            width       = 5,
            polynomial  = 0b00101,
            initial     = 0b11111,

            i_reset     = "-______________",
            i_data      = " 01100000011   ",
            i_shift     = "_-----------___",
            o_crc       = "            ccc"
        )

    def test_token_crc5_nonzero_stall(self):
        self.do(
            width       = 5,
            polynomial  = 0b00101,
            initial     = 0b11111,

            i_reset     = "-_____________________________",
            i_data      = " 0   1   111101110111000011   ",
            i_shift     = "_-___-___-___-___-___------___",
            o_crc       = "                           ccc"
        )

    def test_data_crc16_nonzero(self):
        self.do(
            width       = 16,
            polynomial  = 0b1000000000000101,
            initial     = 0b1111111111111111,

            i_reset     = "-________________________________________________________________________",
            i_data      = " 00000001 01100000 00000000 10000000 00000000 00000000 00000010 00000000 ",
            i_shift     = "_--------_--------_--------_--------_--------_--------_--------_--------_",
            o_crc       =("                                                                        *", [0x94dd])
        )




@module_tester(
    TxBitstuffer,

    i_valid     = (1,),
    i_oe        = (1,),
    i_data      = (1,),
    i_se0       = (1,),

    o_stall     = (1,),
    o_data      = (1,),
    o_se0       = (1,),
    o_oe        = (1,)
)
class TestTxBitstuffer(TestCase):
    def test_passthrough(self):
        self.do(
            i_valid = "_----------",
            i_oe    = "_--------__",
            i_data  = "_--___---__",
            i_se0   = "___________",

            o_stall = "___________",
            o_data  = "__--___---_",
            o_se0   = "___________",
            o_oe    = "__--------_",
        )

    def test_passthrough_se0(self):
        self.do(
            i_valid = "_----------",
            i_oe    = "_--------__",
            i_data  = "_--___---__",
            i_se0   = "____--_____",

            o_stall = "___________",
            o_data  = "__--___---_",
            o_se0   = "_____--____",
            o_oe    = "__--------_",
        )

    def test_bitstuff(self):
        self.do(
            i_valid = "_-----------",
            i_oe    = "_---------__",
            i_data  = "_---------__",
            i_se0   = "____________",

            o_stall = "_______-____",
            o_data  = "__------_--_",
            o_se0   = "____________",
            o_oe    = "__---------_",
        )

    def test_bitstuff_input_stall(self):
        self.do(
            i_valid = "_-___-___-___-___-___-___-___-___-__",
            i_oe    = "_-----------------------------------",
            i_data  = "_-----------------------------------",
            i_se0   = "____________________________________",

            o_stall = "______________________----__________",
            o_data  = "__------------------------____------",
            o_se0   = "____________________________________",
            o_oe    = "__----------------------------------",
        )

    def test_bitstuff_se0(self):
        self.do(
            i_valid = "_-----------__",
            i_oe    = "_-----------__",
            i_data  = "_---------____",
            i_se0   = "__________--__",

            o_stall = "_______-______",
            o_data  = "__------_--___",
            o_se0   = "___________---",
            o_oe    = "__------------",
        )

    def test_bitstuff_at_eop(self):
        self.do(
            i_valid = "_---------____",
            i_oe    = "_---------____",
            i_data  = "_-------______",
            i_se0   = "________--____",

            o_stall = "_______-______",
            o_data  = "__------______",
            o_se0   = "_________-----",
            o_oe    = "__------------",
        )

    def test_multi_bitstuff(self):
        self.do(
            i_valid = "_----------------",
            i_oe    = "_----------------",
            i_data  = "_----------------",
            i_se0   = "_________________",

            o_stall = "_______-______-__",
            o_data  = "__------_------_-",
            o_se0   = "_________________",
            o_oe    = "__---------------",
        )



@module_tester(
    TxNrziEncoder,

    i_valid     = (1,),
    i_oe        = (1,),
    i_data      = (1,),
    i_se0       = (1,),

    o_usbp      = (1,),
    o_usbn      = (1,),
    o_oe        = (1,)
)
class TestTxNrziEncoder(TestCase):
    def test_setup_token(self):
        self.do(
            i_valid = "_--------------------------------------",
            i_oe    = "_----------------------------------____",
            i_data  = "_0000000110110100000000000000100000____",
            i_se0   = "_________________________________--____",

            o_oe    = "___-----------------------------------_",
            o_usbp  = "   _-_-_-___---__-_-_-_-_-_-_-__-_-__- ",
            o_usbn  = "   -_-_-_---___--_-_-_-_-_-_-_--_-____ ",
        )


def encode_data(data):
    """
    Converts array of 8-bit ints into string of 0s and 1s.
    """
    output = ""

    for b in data:
        output += ("{0:08b}".format(b))[::-1]

    return output


# width=5 poly=0x05 init=0x1f refin=true refout=true xorout=0x1f check=0x19 residue=0x06 name="CRC-5/USB"
def crc5_token(addr, ep):
    """
    >>> hex(crc5_token(0, 0))
    '0x2'
    >>> hex(crc5_token(92, 0))
    '0x1c'
    """
    reg = crc.CrcRegister(crc.CRC5_USB)
    reg.takeWord(addr, 7)
    reg.takeWord(ep, 4)
    return reg.getFinalValue()


def crc5_sof(v):
    """
    >>> hex(crc5_sof(1429))
    '0x1'
    >>> hex(crc5_sof(1013))
    '0x5'
    """
    reg = crc.CrcRegister(crc.CRC5_USB)
    reg.takeWord(v, 11)
    return reg.getFinalValue()


def crc16(input_data):
    # width=16 poly=0x8005 init=0xffff refin=true refout=true xorout=0xffff check=0xb4c8 residue=0xb001 name="CRC-16/USB"
    # CRC appended low byte first.
    reg = crc.CrcRegister(crc.CRC16_USB)
    for d in input_data:
        assert d < 256, input_data
        reg.takeWord(d, 8)
    crc16 = reg.getFinalValue()
    return [crc16 & 0xff, (crc16 >> 8) & 0xff]


def nrzi(data, clock_width=4):
    """
    Converts string of 0s and 1s into NRZI encoded string.
    """
    def toggle_state(state):
        if state == 'j':
            return 'k'
        if state == 'k':
            return 'j'
        return state

    prev_state = "k"
    output = ""

    for bit in data:
        # only toggle the state on '0'
        if bit == '0':
            state = toggle_state(state)
        if bit in "jk_":
            state = bit
        output += (state * clock_width)

    return output


def line(data):
    oe = ""
    usbp = ""
    usbn = ""

    for bit in data:
        oe += "-"
        if bit == "j":
            usbp += "-"
            usbn += "_"
        if bit == "k":
            usbp += "_"
            usbn += "-"
        if bit == "_":
            usbp += "_"
            usbn += "_"

    return (oe, usbp, usbn)



def sync():
    return "kjkjkjkk"


def encode_pid(value):
    return encode_data([value | ((0b1111 ^ value) << 4)])


def eop():
    return "__j"


def idle():
    return r"\s+"


# FIXME: SETUP and DATA0 are the same!?
PID_SETUP = 0b1101
PID_DATA0 = 0b0011
PID_ACK   = 0b0010


class TestUsbFsTx_longer(TestCase):
    def do(self, clocks, pid, token_payload, data, expected_output):
        self.output = ""
        name = self.id()

        # create dut
        i_bit_strobe = Signal(1)
        i_pkt_start = Signal(1)
        i_pid = Signal(4)
        i_token_payload = Signal(11)
        i_data_valid = Signal(1)
        i_data_payload = Signal(8)

        dut = UsbFsTx(i_bit_strobe, i_pkt_start, i_pid, i_token_payload, i_data_valid, i_data_payload)

        def clock():
            yield i_data_valid.eq(len(data) > 0)
            if len(data) > 0:
                yield i_data_payload.eq(data[0])
            else:
                yield i_data_payload.eq(0)

            yield

            o_data_get = yield dut.o_data_get
            if o_data_get:
                data.pop(0)

            oe = yield dut.o_oe
            usbp = yield dut.o_usbp
            usbn = yield dut.o_usbn

            if oe == 0:
                self.output += " "
            else:
                if usbp == 0 and usbn == 0:
                    self.output += "_"
                elif usbp == 1 and usbn == 0:
                    self.output += "j"
                elif usbp == 0 and usbn == 1:
                    self.output += "k"
                else:
                    self.output += "!"

        # setup stimulus
        def stim():
            # initiate packet transmission
            yield i_pid.eq(pid)
            yield i_token_payload.eq(token_payload)
            yield i_pkt_start.eq(1)

            yield from clock()

            yield i_pid.eq(0)
            yield i_token_payload.eq(0)
            yield i_pkt_start.eq(0)

            # pump the clock and collect output
            for i in range(clocks):
                yield i_bit_strobe.eq(1)

                yield from clock()

                yield i_bit_strobe.eq(0)

                yield from clock()
                yield from clock()
                yield from clock()

            import re
            m = re.fullmatch(idle() + expected_output + idle(), self.output)
            if m:
                pass
            else:
                raise AssertionError("Packet not found:\n    %s\n    %s" % (expected_output, self.output))


        # run simulation
        run_simulation(dut, stim(), vcd_name="vcd/%s.vcd" % name)


    def test_ack_handshake(self):
        self.do(
            clocks          = 100,
            pid             = PID.ACK,
            token_payload   = 0,
            data            = [],
            expected_output = nrzi(sync() + encode_pid(PID.ACK) + eop())
        )

    def test_empty_data(self):
        self.do(
            clocks          = 100,
            pid             = PID.DATA0,
            token_payload   = 0,
            data            = [],
            expected_output = nrzi(sync() + encode_pid(PID.DATA0) + encode_data([0x00, 0x00]) + eop())
        )

    def test_setup_data(self):
        payload = [0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x00]

        self.do(
            clocks          = 200,
            pid             = PID.SETUP,
            token_payload   = 0,
            data            = payload,
            expected_output = nrzi(sync() + encoude_pid(PID.SETUP) + encoude_data(payload + crc16(payload)) + eop())
        )

    def test_setup_data_bitstuff(self):
        payload = [0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40, 0x3F]
        self.do(
            clocks          = 200,
            pid             = PID.SETUP,
            token_payload   = 0,
            data            = payload,
            expected_output = nrzi(sync() + encode_pid(PID.SETUP) + encode_data([0x80, 0x06, 0x00, 0x01, 0x00, 0x00, 0x40]) + "111111000" + encode_data(crc16(payload)) + eop())
        )


class TestIoBuf(Module):
    def __init__(self):
        self.usb_p = Signal()
        self.usb_n = Signal()

        self.usb_tx_en = Signal()
        self.usb_p_tx = Signal()
        self.usb_n_tx = Signal()

        self.usb_p_rx = Signal()
        self.usb_n_rx = Signal()

        self.usb_p_rx_io = Signal()
        self.usb_n_rx_io = Signal()

        self.comb += [
            If(self.usb_tx_en,
                self.usb_p_rx.eq(0b1),
                self.usb_n_rx.eq(0b0)
            ).Else(
                self.usb_p_rx.eq(self.usb_p_rx_io),
                self.usb_n_rx.eq(self.usb_n_rx_io)
            ),
        ]
        self.comb += [
            If(self.usb_tx_en,
                self.usb_p.eq(self.usb_p_tx),
                self.usb_n.eq(self.usb_n_tx),
            ).Else(
                self.usb_p.eq(self.usb_p_rx),
                self.usb_n.eq(self.usb_n_rx),
            ),
        ]


    def recv(self, v):
        if v == 'i':
            yield self.usb_p_rx_io.eq(0)
            yield self.usb_n_rx_io.eq(1)

        elif v == '0' or v == '_':
            # SE0 - both lines pulled low
            yield self.usb_p_rx_io.eq(0)
            yield self.usb_n_rx_io.eq(0)
        elif v == '1':
            # SE1 - illegal, should never occur
            yield self.usb_p_rx_io.eq(1)
            yield self.usb_n_rx_io.eq(1)
        elif v == '-':
            # ????
            yield self.usb_p_rx_io.eq(1)
            yield self.usb_n_rx_io.eq(0)
        elif v == 'j':
            yield self.usb_p_rx_io.eq(1)
            yield self.usb_n_rx_io.eq(0)
        elif v == 'k':
            yield self.usb_p_rx_io.eq(0)
            yield self.usb_n_rx_io.eq(1)
        else:
            assert False, "Unknown value: %s" % v



def token_packet(pid, addr, endp):
    """Create a token packet for testing.

    sync, pid, addr (7bit), endp(4bit), crc5(5bit), eop

    >>> token_packet(PID.SETUP, 0x0, 0x0)
    '101101000000000001000000'

    >>> token_packet(PID.IN, 0x3, 0x0) # 0x0A
    '100101100110000001010000'

    >>> token_packet(PID.OUT, 0x3a, 0xa)
    '100001111010111011100010'

    >>> token_packet(PID.SETUP, 0x70, 0xa)
    '101101001000011110101010'

    """
    assert addr < 128, addr
    assert endp < 2**4, endp
    assert pid in (PID.OUT, PID.IN, PID.SETUP), token_pid
    data = [addr << 1 | endp >> 3, (endp << 5) & 0xff]
    data[-1] = data[-1] | crc5_token(addr, endp)
    return encode_pid(pid) + encode_data(data)


def data_packet(pid, payload):
    """Create a data packet for testing.

    sync, pid, data, crc16, eop
    FIXME: data should be multiples of 8?

    >>> data_packet(PID.DATA0, [0x80, 0x06, 0x03, 0x03, 0x09, 0x04, 0x00, 0x02])
    '1100001100000001011000001100000011000000100100000010000000000000010000000110101011011100'

    >>> data_packet(PID.DATA1, [])
    '110100100000000000000000'

    """
    assert pid in (PID.DATA0, PID.DATA1), pid
    return encode_pid(pid) + encode_data(payload + crc16(payload))


def handshake_packet(pid):
    """ Create a handshake packet for testing.

    sync, pid, eop
    ack / nak / stall / nyet (high speed only)

    >>> handshake_packet(PID.ACK)
    '01001011'
    >>> handshake_packet(PID.NAK)
    '01011010'
    """
    assert pid in (PID.ACK, PID.NAK, PID.STALL), pid
    return encode_pid(pid)


def sof_packet(frame):
    """Create a SOF packet for testing.

    sync, pid, frame no (11bits), crc5(5bits), eop

    >>> sof_packet(1)
    '101001010000000010111100'

    >>> sof_packet(100)
    '101001010011000011111001'

    >>> sof_packet(257)
    '101001010000010000011100'

    >>> sof_packet(1429)
    '101001010100110110000101'

    >>> sof_packet(2**11 - 2)
    '101001011111111111101011'
    """
    assert frame < 2**11, (frame, '<', 2**11)
    data = [frame >> 3, (frame & 0b111) << 5]
    data[-1] = data[-1] | crc5_sof(frame)
    return encode_pid(PID.SOF) + encode_data(data)


def wrap_packet(data):
    """Add the sync + eop sections and do nrzi encoding.

    >>> wrap_packet(handshake_packet(PID.ACK))
    'kkkkjjjjkkkkjjjjkkkkjjjjkkkkkkkkjjjjjjjjkkkkjjjjjjjjkkkkkkkkkkkk________jjjj'

    """
    return nrzi(sync() + data + eop())


def squash_packet(data):
    return '_'*8 + '_'*len(data) + '_'*30


# one out transaction
# >token, >dataX, <ack

# one in transaction
# >token, <dataX, <ack

# one setup transaction
# >token, >data0, <ack

# setup stage (pid:setup, pid:data0 - 8 bytes, pid:ack)
# [data stage (pid:in+pid:data1, pid:in +pid:data0, ...)]
# status stage (pid:out, pid:data1 - 0 bytes)


# DATA0 and DATA1 PIDs are used in Low and Full speed links as part of an error-checking system.
# When used, all data packets on a particular endpoint use an alternating DATA0
# / DATA1 so that the endpoint knows if a received packet is the one it is
# expecting.
# If it is not it will still acknowledge (ACK) the packet as it is correctly
# received, but will then discard the data, assuming that it has been
# re-sent because the host missed seeing the ACK the first time it sent the
# data packet.


# 1) reset,
#
# 2) The host will now send a request to endpoint 0 of device address 0 to find
#    out its maximum packet size. It can discover this by using the Get
#    Descriptor (Device) command. This request is one which the device must
#    respond to even on address 0.
#
# 3) Then sends a Set Address request, with a unique address to the device at
#    address 0. After the request is completed, the device assumes the new
#    address.
#
#

class TestUsbDevice(TestCase):
    def do(self, packets):
        name = self.id()

        iobuf = TestIoBuf()
        dut = UsbDevice(iobuf, 0)

        recieved_bytes = []
        recieved_byte = Signal(8)
        sending_bytes = []
        sending_byte = Signal(8)

        def clock(data):
            for v in data:
                # Pull bytes from sending_bytes
                yield dut.endp_ins[0].valid.eq(len(sending_bytes) > 0)
                if len(sending_bytes) > 0:
                    yield sending_byte.eq(sending_bytes[0])
                    yield dut.endp_ins[0].payload.data.eq(sending_bytes[0])

                    ready = yield dut.endp_ins[0].ready
                    if ready:
                        sending_bytes.pop(0)

                yield from dut.iobuf.recv(v)

                # Push bytes into received_bytes
                valid = yield dut.endp_outs[0].valid
                if valid:
                    yield recieved_byte.eq(dut.endp_outs[0].payload.data)
                    data = yield dut.endp_outs[0].data
                    recieved_bytes.append(data)

                yield

        idle_signal = Signal(1)

        def idle():
            yield from dut.iobuf.recv('i')
            yield idle_signal.eq(1)
            for i in range(0, 8):
                yield
            yield idle_signal.eq(0)

        # setup stimulus
        def stim():
            yield dut.endp_outs[0].ready.eq(1)

            yield from dut.iobuf.recv('-')
            yield from idle()

            for recv, send in packets:
                if recv is None and send is None:
                    print("-"*50)
                    continue

                if recv is not None:
                    recv_pkt, expected_bytes = recv
                    recieved_bytes.clear()
                    yield from clock(recv_pkt)
                    print("Received", recieved_bytes, "(expected: %s)" % repr(expected_bytes))
                    #self.assertSequenceEqual(recieved_bytes, expected_bytes, "%s %s" % (recv_pkt, expected_bytes))

                if send is not None:
                    sending_bytes.clear()
                    send_pkt, data_bytes = send

                    sending_bytes.extend(data_bytes)
                    print("Sending", sending_bytes)
                    yield from clock(squash_packet(send_pkt))
                    print("Remaining", sending_bytes)
                    #assert len(sending_bytes) == 0, sending_bytes

                yield from idle()


        # run simulation
        run_simulation(dut, stim(), vcd_name="vcd/%s.vcd" % name)

    def test_setup_data(self):

        packets = []

        #packets.append((
        #   (<packet host->device>, <expected received data>),
        #   (<packet device->host>, <data to feed>),
        # ))
        # ----------------------------

        packets.append((
            (wrap_packet(token_packet(PID.SETUP, 0, 0)), []),
            None,
        ))
        d = [0x80, 0x06, 0x00, 0x06, 0x00, 0x00, 0x0A, 0x00]
        packets.append((
            (wrap_packet(data_packet(PID.DATA0, d)), d+crc16(d)),
            None,
        ))
        packets.append((
            None,
            (wrap_packet(handshake_packet(PID.ACK)), []),
        ))
        packets.append((None, None))

        # ============================
        # Setup Stage
        # ----------------------------
        # ->pid:setup
        packets.append((
            (wrap_packet(token_packet(PID.SETUP, 0, 0)), []),
            None,
        ))
        # ->pid:data0 [80 06 00 06 00 00 0A 00] # Get descriptor, Index 0, Type 03, LangId 0000, wLength 10?
        d = [0x80, 0x06, 0x00, 0x06, 0x00, 0x00, 0x0A, 0x00]
        packets.append((
            (wrap_packet(data_packet(PID.DATA0, d)), d+crc16(d)),
            None,
        ))
        # <-pid:ack
        packets.append((
            None,
            (wrap_packet(handshake_packet(PID.ACK)), []),
        ))

        packets.append((
            ('-'*2000, []),
            None,
        ))

        # Data Stage
        # ----------------------------
        # 12 byte descriptor, max packet size 8 bytes

        # First 8 bytes
        # ->pid:in
        packets.append((
            (wrap_packet(token_packet(PID.IN, 0, 0)), []),
            None,
        ))
        # <-pid:data1 [00 01 02 03 04 05 06 07]
        d = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07]
        packets.append((
            None,
            (wrap_packet(data_packet(PID.DATA1, d)), d),
        ))
        # ->pid:ack
        packets.append((
            (wrap_packet(handshake_packet(PID.ACK)), []),
            None,
        ))

        # Remaining 4 bytes + padding
        # ->pid:in
        packets.append((
            (wrap_packet(token_packet(PID.IN, 0, 0)), []),
            None,
        ))
        # <-pid:data0 [08 09 0A 0B 00 00 00 00]
        d = [0x08, 0x09, 0x0A, 0x0B, 0x00, 0x00, 0x00, 0x00]
        packets.append((
            None,
            (wrap_packet(data_packet(PID.DATA0, d)), d),
        ))
        # ->pid:ack
        packets.append((
            (wrap_packet(handshake_packet(PID.ACK)), []),
            None,
        ))

        packets.append((
            ('-'*2000, []),
            None,
        ))

        # Status Stage
        # ----------------------------
        # ->pid:out
        packets.append((
            (wrap_packet(token_packet(PID.OUT, 0, 0)), []),
            None,
        ))
        # ->pid:data1 []
        packets.append((
            (wrap_packet(data_packet(PID.DATA1, [])), []),
            None,
        ))
        # <-pid:ack
        packets.append((
            None,
            (wrap_packet(handshake_packet(PID.ACK)), []),
        ))
        # ============================

        packets.append((None, None))

        # ----------------------------
        # ->pid:setup
        # ->pid:data0 [80 06 00 03 00 00 40 00] # Get descriptor, Index 0, Type 03, LangId 0000, wLength 64
        # <-pid:ack

        # ->pid:in
        # <-pid:nak

        # ->pid:in
        # ->pid:data1 [04 03 09 04] # String descriptor, bLength 4, bDescriptorType 0x3 (String), wLangId: 0x0409 (Eng US)
        # <-pid:ack

        # ->pid:in
        # ->pid:data1 []
        # <-pid:ack

        # ->pid:setup
        # ->pid:data0 [80 06 03 03 09 04 00 02]
        # <-pid:ack

        # ->pid:in
        # ->pid:data1 [12 03 30 00 30 00 33 00 44 00 39 00 34 00 34 00 41 00]
        # <-pid:ack

        # ->pid:in
        # ->pid:data1 []
        # <-pid:ack

        # ->pid:setup
        # ->pid:data0 [21 09 41 03 00 02 00]
        # <-pid:ack
        # ->pid:out
        # <-pid:data1 [41 01]
        # <-pid:nak
        # ->pid:out
        # <-pid:data1 [41 01]
        # <-pid:ack
        # ->pid:in
        # <-pid:nak
        # ->pid:in
        # <-pid:data1 []
        # <-pid:ack



        # up addr 0 ep 0

        # data 1 [12 01 00 02 02 00 00 20 50 1D 30 61 00 00 00 00 00 01]

        # ack

        # out addr 0 ep 0

        # data 1 []

        # ack
        self.do(packets)




if __name__ == '__main__':
    import doctest
    doctest.testmod()
    unittest.main()