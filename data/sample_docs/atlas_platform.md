# Atlas P2 platform

The Atlas P2 is the current flagship autonomous mobile robot from Auralis
Dynamics. It moves pallets and heavy totes between goods-in, storage, and
packing zones without fixed infrastructure such as magnetic strips or QR grids.

## Key specifications

Payload capacity: the Atlas P2 carries up to 450 kg on its standard load deck.
Top speed is 1.8 m/s in mixed traffic areas and 2.2 m/s in robot-only aisles.
Runtime on a single charge: the Atlas P2 runs for 14 hours of continuous
operation. A fast-charge dock restores a full charge in 45 minutes, and robots
opportunity-charge during natural idle windows.

## Navigation

The Atlas P2 navigates with a combination of 360-degree safety lidar and visual
SLAM cameras. Maps are built during a survey walk and updated continuously in
operation. No floor markers, reflectors, or wires are required, so layout
changes do not require re-installation.

## Atlas Hive fleet software

Atlas Hive is the fleet management layer for every Atlas robot. It handles job
assignment, traffic control, charging strategy, and live analytics. Hive
exposes a REST API and webhooks for integration with warehouse management
systems. Hive dashboards report throughput, robot utilisation, and exception
rates per zone.
