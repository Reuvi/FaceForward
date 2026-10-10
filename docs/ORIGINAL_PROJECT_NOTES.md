# Original project instructions and team notes

Source: Reuvi's original project brief, shared on October 10, 2026. The original
wording is retained below, with Markdown formatting and spacing cleaned up.
Logistics and reminders are historical notes from that brief.

Agents: read these notes before implementing a component. They describe the team's
original intent. `PROJECT_PLAN.md` organizes the implementation work, while
`Contracts/README.md` contains proposed technical conventions added during setup.
Do not confuse those implementation choices with requirements stated in these
original notes. Later explicit team decisions take precedence; call out unresolved
differences instead of silently rewriting the original brief.

## Original repository and agent instructions

> Hey I am doing a hackthon, you have two direct instructions.
>
> 1) clione this repo that we are using, and make sure you can edit it three people
> are going to be working on it simultaneously
>
> 2) I want you to create a structure for all of our agents to work on it and
> instructions for other agents to use so they dont have interference with coding.

Repository subsequently supplied: [app0cal/hackathon26](https://github.com/app0cal/hackathon26).

## Original team notes

Reminder to join the team after 2pm

Reuvi

[reuvi_israeli@icloud.com](mailto:reuvi_israeli@icloud.com)

Aria Cai

[ariacai0306@gmail.com](mailto:ariacai0306@gmail.com)

github: c0c-wow

## Project plan

Main components:

Computer vision -> processing -> drivers

A user friendly human–computer interface for severely movement impaired persons
should fulfill several conditions: first of all, it should be non-contact and
avoid specialized equipment, it should feature real-time performance, and it
should run on a consumer-grade computer.

## Computer Vision

Core Idea: Treat the face as a signal, components of the face that we choose to
use for propagating state will be sampled using computer vision. The mapping of
these specific actions will be decided later when creating connections to certain
device drivers and processing for optimization.

1. It should have a higher sampling rate and a fast detection rate. We will
   interpolate between values. For most facial functions it will be an on or off.
   Some of them will be an area boundary (tongue, head movement).
2. It should be easy to do, no weird facial movements or impractical expressions
   to make input into our general controller.
3. It should be able to run on a consumer device fast and efficiently.

- Important distinctions: The main software should configure the camera per a
  person's profile so the camera can be transferred onto that person's facial
  features and symmetry. The maximum number of people we want the cameras
  detecting is 2.

Storyboard process -> A user downloads the main app -> they set up a profile so
the AI model can be optimized for their facial features -> It should also test
each signal detection and adjust specific properties so the signal detection
rate reduces false positives. Once configured for a user profile it should run
in the background and continuously keep reading these signals. How the signals
actually effect a movement of a specific device should design later on in the
processing. Their will be a second phase of the setup for each specific device
you want to use.

IE after the detection is set up then we will configure how each signal is
represented mathematically.

Currently these are the signals we want to continuously track while the app is
running

- Pupil tracking
- tongue tracking
- Each specific eye open or closed
- Head vertical direction / bias
- head horizontal direction / bias

For implementing this we want to have a test software for development that will
allow us to see what its tracking and a graphical interface of the signals like
on an oscilloscope. The sampling rate and everything will be customizable to fit
a specific user or our best use case application.

## Processing

This is the intermediate phase between signal detection and relaying it to the
drivers. This represents each detection of a specific device driver. There are
three types of actions, buttons, joy sticks, and scroll wheels.

Buttons are 0 dimensional on and off, but they can have different thresholds for
how long it needs to be down for to be activated.

Scroll wheels have 1 dimension: Up and down vertically. This would be controlled
by head actions, the more bias towards a direction the more velocity we would
want to apply to these data and the higher control. Their is also going to be
unique thresholds. And we can customize it per person

Joysticks has 2 dimensions UP and down and left and right (eye pupils and tongue
locations around the mouth) How far out they are can determine intensity and
where they are with respect to a central reference point.

All these sensitivities should be customizable and fit for a user we want to
calibrate to our faces.

## Drivers

Values for the MVP should assume inputs from the range

(0,1) so values like .88 , .12, etc

First edition is testing the values by having a

Mouse keyboard combo and attempting to mimic it based off the values imputed
(for now it will be any number in the range 0 to 1. The main goals here are the

- Scroll
- Left click a
- Right click
- Delete
- Insert

Additional button to prompt speech to text because trying to have facial movement
mapped to all possible keys would be difficult.

Next steps are mimicking an Xbox controller esq device that we can use to control
the joystick and buttons it has.

## Subsequent team clarification

Reuvi clarified the division of work:

> 1 person is working on each section kinda.

Use roughly one person per section: Vision, Processing, and Drivers. Their agents
work within that section. Coordinate cross-section changes and shared interfaces;
integration is a responsibility held by one of the three people.
