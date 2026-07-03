<?php
include "../responsive/Framework.php";
$framework->getForm();
$framework->configure(
        array(
            'item_name' => "Hiab HiPro 262E Crane + Truck Package for Sale | Atlas Polar",
            'short_name' => "Hiab HiPro 262E Crane + Truck Package for Sale | Atlas Polar",
            'description' => "The Hiab HiPro 262E is a truck-mounted crane featuring Hiab's CombiDrive Radio Remotes, Space X4 Elctronic Safety System, FTLS, mounted on a truck.",
            'menu_url' => "/demo-used-equipment/hiab-hipro-262e-4-jib-70x3-international-mv-tandem-package-for-sale.html",
            'media_path' => 'demo-used-equipment/hiab-boom-trucks/hiab-hipro-262e-4-jib-70x3-international-mv-tandem-package-for-sale/',
            'title' => 'Hiab HiPro 262E Crane + Truck Package for Sale | Atlas Polar'
        )
);
$framework->build_header();
?>
<div class="ppc">
<h1 itemprop="headline" class="product-heading">
    <?php $framework->build_image('/media/material-handling-equipment/hiab/hiab-logo.svg', 'HIAB Boom Truck Package', 'height="25" class="small-logo"'); ?> Hiab HiPro 262E Crane + Truck - Work-Ready Package for Sale</h1>
<div class="top-content">
    <div id="product-img">
        <?php $framework->build_sirv_video("https://blueprint.sirv.com/atlas-polar/hiab-hipro-262e-4-jib-70x3-international-mv-tandem-package-for-sale.mp4"); ?>
		<?php
		$framework->build_gallery(array(
			array('1.jpg', 'Hiab HiPro 262E Crane + Truck Package for Sale | Atlas Polar'),
			array('2.jpg', 'Hiab HiPro 262E Crane + Truck Package for Sale | Atlas Polar'),
			array('3.jpg', 'Hiab HiPro 262E Crane + Truck Package for Sale | Atlas Polar'),
		));
		?>
    </div>
    <div class="feature-bullets">

		<form class="product-quote-form" id="quote-form" method="post" action="/material-handling-equipment/m-info-request.php">
		<h4>Get a quote by calling <a href="tel:6472902764">647.290.2764</a> or complete the form below.</h4>
		<?php $framework->quoteform(false); ?>
		<input type="submit" value="Get a Quote" />
		</form>
    </div>
</div>

<div class="demo-used-info">
<div class="demo-used-block">
    <h3><?php $framework->build_image('../../icon-crane.png', 'HIAB Boom Truck Package'); ?> HIAB Boom Truck Package Details</h3>
    <table>
        <tr>
            <th>Model:</th>
            <td>Hiab HiPro 262E-4+Jib 70x3</td>
        </tr>
        <tr>
            <th>Year:</th>
            <td>2023</td>
        </tr>
        <tr>
            <th>Lifting Capacity:</th>
            <td>1,540 @ 59&#x27;1&quot;/ 1,940lbs @ 48&#x27;7&quot; with JIB/ 11,680 lbs@14&#x27;1&quot;/ 3,920 lbs @ 38&#x27;1&quot; with out Jib</td>
        </tr>
        <tr>
            <th>No of Hydraulic Extensions:</th>
            <td>4 on main, 3 on jib</td>
        </tr>
        <tr>
            <th>Hydraulic Outreach:</th>
            <td>71&#x27;10&quot; with Jib/ 38&#x27;5&quot; with out JIB Horizontal</td>
        </tr>
        <tr>
            <th>Accessories:</th>
            <td>Hiab&#x27;s CombiDrive Radio Remotes, Space X4 Elctronic Safety System, FTLS LED perimeter Safety Light System, Read HD Camers</td>
        </tr>
    </table>
</div>
<div class="demo-used-block right">
	<h3><?php $framework->build_image('../../icon-truck.png', 'Truck'); ?> Truck Details</h3>
    <table>
        <tr>
            <th>Make:</th>
            <td>International</td>
        </tr>
        <tr>
            <th>Model:</th>
            <td>MV Tandem</td>
        </tr>
        <tr>
            <th>Year:</th>
            <td>new</td>
        </tr>
        <tr>
            <th>Mileage:</th>
            <td>new</td>
        </tr>
        <tr>
            <th>Engine:</th>
            <td>Cummins L9</td>
        </tr>
        <tr>
            <th>Horsepower:</th>
            <td>350 hp</td>
        </tr>
        <tr>
            <th>Transmission:</th>
            <td>Allison automatic</td>
        </tr>
        <tr>
            <th>Deck Length:</th>
            <td>22&#x27; steel deck with 8 winch &amp; straps, rub rails &amp; stake pockets</td>
        </tr>
        <tr>
            <th>GVW:</th>
            <td>60,000 lbs</td>
        </tr>
        <tr>
            <th>Suspension:</th>
            <td>Air Ride</td>
        </tr>
        <tr>
            <th>Comments:</th>
            <td>A perfect work truck ready to go!</td>
        </tr>
    </table>
</div>
<div class="demo-used-block">
    <h3>Contact Details</h3>
    <table>
		<tr>
            <th>Nick Georgoussis</th><td><a href="tel:6472902764">647.290.2764</a></td>
        </tr>
    </table>
</div>
</div>
</div>
<?php $framework->build_footer(); ?>
